# -*- coding: utf-8 -*-
"""
LLM服务模块 - 大语言模型服务封装

功能:
- 异步聊天接口（普通 + 流式）
- 多提供商支持
- 指数退避重试
- 配置管理
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Type

import httpx

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# 本地定义，避免顶层 import core（core 不在 backend 的 sys.path 中）
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """LLM响应数据类"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict] = None


class LLMServiceError(Exception):
    """LLM服务错误"""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


# ---------------------------------------------------------------------------
# 延迟加载 app.core.llm_providers
# ---------------------------------------------------------------------------

def _load_providers():
    """延迟加载 llm_providers 模块"""
    from app.core import llm_providers
    return llm_providers


def get_provider(name: str):
    """获取提供商类"""
    mod = _load_providers()
    return mod.get_provider(name)


def get_all_providers() -> List[Dict[str, Any]]:
    """获取所有提供商信息"""
    mod = _load_providers()
    return mod.get_all_providers()


async def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> None:
    """指数退避等待"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    await asyncio.sleep(delay)


class LLMService:
    """LLM服务 - 异步封装"""

    def __init__(self):
        self._provider = None
        self._provider_name: str = ""
        self._api_key: str = ""
        self._api_url: str = ""
        self._model: str = ""

    # ---- 配置 ----

    def configure(
        self,
        provider_name: str,
        api_key: str,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """配置LLM提供商"""
        provider_cls = get_provider(provider_name)
        self._provider_name = provider_name
        self._api_key = api_key
        self._api_url = api_url or provider_cls.default_api_url
        self._model = model or provider_cls.default_model
        self._provider = provider_cls(
            api_key=api_key,
            api_url=self._api_url,
            model=self._model,
        )
        logger.info("LLM服务已配置: provider=%s, model=%s", provider_name, self._model)

    @property
    def is_configured(self) -> bool:
        return self._provider is not None and bool(self._api_key)

    # ---- 非流式聊天 ----

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 2,
        **kwargs,
    ) -> LLMResponse:
        """异步聊天（非流式）"""
        if not self.is_configured:
            raise LLMServiceError("LLM服务未配置")

        mod = _load_providers()
        LLMProviderError = mod.LLMProviderError

        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    _executor,
                    lambda: self._provider.chat(messages, **kwargs),
                )
                # 将 core 的 LLMResponse 转为本模块的 LLMResponse
                return LLMResponse(
                    content=response.content,
                    model=response.model,
                    usage=response.usage,
                    raw_response=response.raw_response,
                )
            except LLMProviderError as e:
                last_error = e
                if e.retryable and attempt < max_retries:
                    await exponential_backoff(attempt)
                    continue
                raise LLMServiceError(str(e), retryable=e.retryable) from e
            except Exception as e:
                raise LLMServiceError(f"LLM调用失败: {e}") from e

        raise LLMServiceError(str(last_error)) from last_error

    # ---- 流式聊天 ----

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> AsyncIterator[str]:
        """异步流式聊天，逐块 yield 文本"""
        if not self.is_configured:
            raise LLMServiceError("LLM服务未配置")

        url = self._provider._get_chat_endpoint()
        headers = self._provider._get_headers()
        payload = self._provider._build_payload(messages, **kwargs)
        payload["stream"] = True

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise LLMServiceError(
                            f"API错误 ({resp.status_code}): {body.decode(errors='replace')}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except Exception:
                            continue
        except LLMServiceError:
            raise
        except Exception as e:
            raise LLMServiceError(f"流式调用失败: {e}") from e

    # ---- 连接测试 ----

    async def test_connection(self) -> Tuple[bool, str]:
        """测试连接"""
        if not self.is_configured:
            return False, "LLM服务未配置"
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                _executor, self._provider.test_connection
            )
        except Exception as e:
            return False, f"连接测试失败: {e}"

# -*- coding: utf-8 -*-
"""
配置管理模块（轻量版）

所有持久化配置统一存储在 SQLite 数据库中（通过 SettingsService）。
此模块仅提供：
- 默认配置值
- 环境变量覆盖
- 运行时内存配置（由 SettingsService 注入）

不再读写 data/settings.json 文件。
"""

import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 默认配置
_DEFAULTS = {
    "llm_provider": "siliconflow",
    "api_base_url": "",
    "api_key": "",
    "model_name": "Qwen/Qwen3-8B",
    "max_tokens": 2048,
    "temperature": 0.7,
    "api_timeout": 30,
    "embedding_model": "bge-large-zh",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "chunk_max_per_item": 10,
    "retrieval_top_k": 5,
    "similarity_threshold": 0.4,
    "history_max_messages": 12,
    "history_max_chars": 6000,
    "context_max_chars": 4000,
    "context_top_n": 3,
}

# 环境变量映射
_ENV_MAP = {
    "api_key": ["RAGPROJECT_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"],
    "api_base_url": ["RAGPROJECT_API_BASE_URL", "SILICONFLOW_API_BASE_URL", "OPENAI_BASE_URL"],
}


class Config:
    """轻量配置类 — 默认值 + 环境变量 + 运行时注入"""

    _instance = None
    _runtime: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------ 环境变量 ------
    @staticmethod
    def _get_env_override(key: str) -> Optional[str]:
        for env_key in _ENV_MAP.get(key, []):
            val = os.environ.get(env_key, "").strip()
            if val:
                return val
        return None

    # ------ 公开接口 ------
    def get(self, key: str, default: Any = None, include_env: bool = True) -> Any:
        """获取配置项，优先级：运行时注入 > 环境变量 > 默认值"""
        # 运行时注入（由 sync_config_from_db 写入）
        if key in self._runtime:
            return self._runtime[key]

        # 环境变量
        if include_env:
            env_val = self._get_env_override(key)
            if env_val is not None:
                return env_val

        return _DEFAULTS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """运行时设置配置项（仅内存，不持久化）"""
        self._runtime[key] = value

    def get_all(self) -> dict:
        merged = dict(_DEFAULTS)
        merged.update(self._runtime)
        return merged

    def update(self, settings: dict) -> None:
        if isinstance(settings, dict):
            self._runtime.update(settings)

    def reload(self) -> None:
        """清空运行时配置"""
        self._runtime.clear()

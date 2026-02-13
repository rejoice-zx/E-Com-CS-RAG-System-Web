# -*- coding: utf-8 -*-
"""
对话API - 依赖注入（LLM服务 & RAG服务）

将全局 _llm_service / _llm_service_configured 改为 FastAPI 依赖，
避免模块级全局可变状态在多进程环境下的潜在问题。
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.chat_service import ChatService
from app.models.user import User
from app.models.conversation import Conversation
from app.api.dependencies import get_optional_user, get_customer_id_from_token

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)


class LLMServiceManager:
    """LLM 服务管理器（进程内单例）"""

    def __init__(self):
        self._service: LLMService = None
        self._configured: bool = False

    @property
    def service(self) -> LLMService:
        if self._service is None:
            self._service = LLMService()
        return self._service

    @property
    def configured(self) -> bool:
        return self._configured

    async def configure_from_db(self, db: AsyncSession) -> LLMService:
        """从数据库配置加载LLM服务"""
        from app.services.settings_service import SettingsService

        llm_config = await SettingsService.get_llm_config(db)
        svc = self.service

        if llm_config.api_key:
            svc.configure(
                provider_name=llm_config.provider,
                api_key=llm_config.api_key,
                api_url=llm_config.api_url or None,
                model=llm_config.model or None,
            )
            self._configured = True

        return svc


# 进程内单例
_llm_manager = LLMServiceManager()


async def get_rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    """FastAPI 依赖：根据数据库配置构建 RAG 服务实例"""
    from app.services.settings_service import SettingsService

    try:
        rag_config = await SettingsService.get_rag_config(db)
        retrieval_top_k = max(1, int(rag_config.top_k))

        from app.core.config import Config as _CfgHelper
        _cfg_helper = _CfgHelper()
        context_top_n = int(_cfg_helper.get("context_top_n", 3))
        context_top_n = min(context_top_n, retrieval_top_k)

        return RAGService(
            similarity_threshold=rag_config.similarity_threshold,
            retrieval_top_k=retrieval_top_k,
            context_max_chars=rag_config.max_context_length,
            context_top_n=context_top_n,
            use_rewrite=rag_config.use_rewrite,
        )
    except Exception as e:
        logger.warning(f"加载RAG配置失败，使用默认值: {e}")
        return RAGService()


def get_llm_service() -> LLMService:
    """FastAPI 依赖：获取 LLM 服务实例"""
    return _llm_manager.service


async def get_configured_llm_service(
    db: AsyncSession = Depends(get_db),
) -> LLMService:
    """FastAPI 依赖：获取已从数据库加载配置的 LLM 服务"""
    return await _llm_manager.configure_from_db(db)


def _is_staff_user(user: Optional[User]) -> bool:
    return bool(user and user.role in ("admin", "cs"))


def require_chat_customer_id(
    customer_id: Optional[str] = Depends(get_customer_id_from_token),
) -> str:
    """要求 chat 接口必须携带有效 token（guest 或登录用户）。"""
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或无效的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return customer_id


async def get_authorized_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    customer_id: str = Depends(require_chat_customer_id),
) -> Conversation:
    """
    获取当前请求可访问的会话。
    - admin/cs 可访问任意会话
    - 其他角色仅可访问 customer_id 与 token 一致的会话
    """
    conversation = await ChatService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )

    if not _is_staff_user(current_user) and conversation.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该对话",
        )

    return conversation

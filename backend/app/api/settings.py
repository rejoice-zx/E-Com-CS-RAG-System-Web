# -*- coding: utf-8 -*-
"""Settings Management API Endpoints"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.dependencies import require_admin
from app.models.user import User
from app.services.settings_service import (
    SettingsService,
    LLMConfig,
    EmbeddingConfig,
    RAGConfig,
    GeneralConfig,
)
from app.schemas.settings import (
    SettingsResponse,
    SettingsUpdateRequest,
    LLMConfigResponse,
    EmbeddingConfigResponse,
    RAGConfigResponse,
    GeneralConfigResponse,
    LLMProvidersResponse,
    LLMProviderInfo,
    TestConnectionRequest,
    TestConnectionResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    获取系统设置
    
    需要管理员权限
    
    返回:
    - LLM配置（API密钥已遮蔽）
    - Embedding配置
    - RAG配置
    """
    config = await SettingsService.get_all_settings(db)
    
    return SettingsResponse(
        llm=LLMConfigResponse(
            provider=config.llm.provider,
            api_key_masked=SettingsService.mask_api_key(config.llm.api_key),
            api_url=config.llm.api_url,
            model=config.llm.model,
            has_api_key=bool(config.llm.api_key),
        ),
        embedding=EmbeddingConfigResponse(
            provider=config.embedding.provider,
            api_key_masked=SettingsService.mask_api_key(config.embedding.api_key),
            api_url=config.embedding.api_url,
            model=config.embedding.model,
            dimension=config.embedding.dimension,
            has_api_key=bool(config.embedding.api_key),
        ),
        rag=RAGConfigResponse(
            top_k=config.rag.top_k,
            similarity_threshold=config.rag.similarity_threshold,
            use_rewrite=config.rag.use_rewrite,
            max_context_length=config.rag.max_context_length,
            chunk_size=config.rag.chunk_size,
            chunk_overlap=config.rag.chunk_overlap,
        ),
        general=GeneralConfigResponse(
            timezone=config.general.timezone,
        ),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    更新系统设置
    
    需要管理员权限
    
    参数:
    - llm: LLM配置（可选）
    - embedding: Embedding配置（可选）
    - rag: RAG配置（可选）
    
    返回:
    - 更新后的设置
    """
    # 获取当前配置
    current_config = await SettingsService.get_all_settings(db)
    
    # 更新LLM配置
    llm_config = None
    if request.llm:
        llm_config = LLMConfig(
            provider=request.llm.provider,
            api_key=request.llm.api_key if request.llm.api_key else current_config.llm.api_key,
            api_url=request.llm.api_url or "",
            model=request.llm.model or "",
        )
    
    # 更新Embedding配置
    embedding_config = None
    if request.embedding:
        embedding_config = EmbeddingConfig(
            provider=request.embedding.provider or current_config.embedding.provider,
            api_key=request.embedding.api_key if request.embedding.api_key else current_config.embedding.api_key,
            api_url=request.embedding.api_url or current_config.embedding.api_url,
            model=request.embedding.model or current_config.embedding.model,
            dimension=request.embedding.dimension or current_config.embedding.dimension,
        )
    
    # 更新RAG配置
    rag_config = None
    if request.rag:
        rag_config = RAGConfig(
            top_k=request.rag.top_k,
            similarity_threshold=request.rag.similarity_threshold,
            use_rewrite=request.rag.use_rewrite,
            max_context_length=request.rag.max_context_length,
            chunk_size=request.rag.chunk_size,
            chunk_overlap=request.rag.chunk_overlap,
        )
    
    # 更新通用配置
    general_config = None
    if request.general:
        general_config = GeneralConfig(
            timezone=request.general.timezone or current_config.general.timezone,
        )
    
    # 保存更新
    await SettingsService.update_settings(db, llm_config, embedding_config, rag_config, general_config)

    # ── 审计日志：记录配置变更（不记录 API Key 明文） ──
    changed_sections: list[str] = []
    if llm_config:
        changed_sections.append(
            f"LLM(provider={llm_config.provider}, model={llm_config.model}, "
            f"api_url={llm_config.api_url}, api_key_changed={bool(request.llm and request.llm.api_key)})"
        )
    if embedding_config:
        changed_sections.append(
            f"Embedding(provider={embedding_config.provider}, model={embedding_config.model}, "
            f"dimension={embedding_config.dimension}, "
            f"api_key_changed={bool(request.embedding and request.embedding.api_key)})"
        )
    if rag_config:
        changed_sections.append(
            f"RAG(top_k={rag_config.top_k}, threshold={rag_config.similarity_threshold}, "
            f"rewrite={rag_config.use_rewrite}, max_ctx={rag_config.max_context_length}, "
            f"chunk={rag_config.chunk_size}/{rag_config.chunk_overlap})"
        )
    if general_config:
        changed_sections.append(f"General(timezone={general_config.timezone})")
    if changed_sections:
        logger.info(
            "系统设置变更 | operator=%s (id=%d) | %s",
            current_user.username, current_user.id, " | ".join(changed_sections),
        )
    
    # 时区变更时同步到日志格式化器
    if general_config and general_config.timezone:
        from app.main import get_log_formatter
        get_log_formatter().set_timezone(general_config.timezone)

    # 同步 chunk 配置到运行时 Config，使 knowledge_service 立即生效
    if rag_config:
        from app.core.config import Config as RuntimeConfig
        _cfg = RuntimeConfig()
        _cfg.set("chunk_size", rag_config.chunk_size)
        _cfg.set("chunk_overlap", rag_config.chunk_overlap)
    
    # 返回更新后的配置
    updated_config = await SettingsService.get_all_settings(db)
    
    return SettingsResponse(
        llm=LLMConfigResponse(
            provider=updated_config.llm.provider,
            api_key_masked=SettingsService.mask_api_key(updated_config.llm.api_key),
            api_url=updated_config.llm.api_url,
            model=updated_config.llm.model,
            has_api_key=bool(updated_config.llm.api_key),
        ),
        embedding=EmbeddingConfigResponse(
            provider=updated_config.embedding.provider,
            api_key_masked=SettingsService.mask_api_key(updated_config.embedding.api_key),
            api_url=updated_config.embedding.api_url,
            model=updated_config.embedding.model,
            dimension=updated_config.embedding.dimension,
            has_api_key=bool(updated_config.embedding.api_key),
        ),
        rag=RAGConfigResponse(
            top_k=updated_config.rag.top_k,
            similarity_threshold=updated_config.rag.similarity_threshold,
            use_rewrite=updated_config.rag.use_rewrite,
            max_context_length=updated_config.rag.max_context_length,
            chunk_size=updated_config.rag.chunk_size,
            chunk_overlap=updated_config.rag.chunk_overlap,
        ),
        general=GeneralConfigResponse(
            timezone=updated_config.general.timezone,
        ),
    )


@router.get("/llm-providers", response_model=LLMProvidersResponse)
async def get_llm_providers(
    current_user: User = Depends(require_admin())
):
    """
    获取LLM提供商列表
    
    需要管理员权限
    
    返回:
    - 支持的LLM提供商列表（名称、默认API地址、支持的模型）
    """
    providers = SettingsService.get_llm_providers()
    
    return LLMProvidersResponse(
        providers=[
            LLMProviderInfo(
                name=p["name"],
                display_name=p["display_name"],
                default_api_url=p["default_api_url"],
                default_model=p["default_model"],
                supported_models=p["supported_models"],
            )
            for p in providers
        ]
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_llm_connection(
    request: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    测试LLM API连接
    
    需要管理员权限
    
    参数:
    - provider: 提供商名称
    - api_key: API密钥（可选，不传则使用已保存的）
    - api_url: API地址（可选）
    - model: 模型名称（可选）
    
    返回:
    - 连接测试结果
    """
    # 如果没有传入api_key，使用已保存的
    api_key = request.api_key
    if not api_key:
        current_config = await SettingsService.get_all_settings(db)
        api_key = current_config.llm.api_key
    
    if not api_key:
        return TestConnectionResponse(
            success=False,
            message="请先配置API密钥"
        )
    
    success, message = await SettingsService.test_llm_connection(
        provider=request.provider,
        api_key=api_key,
        api_url=request.api_url,
        model=request.model,
    )
    
    return TestConnectionResponse(
        success=success,
        message=message
    )

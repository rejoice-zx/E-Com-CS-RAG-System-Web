# -*- coding: utf-8 -*-
"""
知识库API端点 - Knowledge API

功能:
- 知识库CRUD操作
- 分页和筛选
- 导入导出
- 向量索引管理
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json

from app.database import get_db
from app.api.dependencies import AdminRequired
from app.models.user import User
from app.services.knowledge_service import knowledge_service
from app.schemas.knowledge import (
    CreateKnowledgeRequest,
    UpdateKnowledgeRequest,
    KnowledgeResponse,
    KnowledgeListResponse,
    ImportKnowledgeRequest,
    ImportKnowledgeResponse,
    ExportKnowledgeResponse,
    IndexStatusResponse,
    RebuildIndexResponse
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=KnowledgeListResponse)
async def get_knowledge_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category: Optional[str] = Query(None, description="分类筛选"),
    keyword: Optional[str] = Query(None, description="关键词筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    获取知识列表（分页、筛选）
    
    - 需要管理员权限
    - 支持按分类和关键词筛选
    """
    items, total = await knowledge_service.get_knowledge_list(
        db=db,
        page=page,
        page_size=page_size,
        category=category,
        keyword=keyword
    )
    
    return KnowledgeListResponse(
        items=[KnowledgeResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    request: CreateKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    添加知识条目
    
    - 需要管理员权限
    - 自动检查重复
    - 自动同步向量索引
    """
    # 检查重复
    duplicate = await knowledge_service.check_duplicate(db, request.question)
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识条目已存在（问题重复）"
        )
    
    item = await knowledge_service.create_knowledge(
        db=db,
        question=request.question,
        answer=request.answer,
        keywords=request.keywords,
        category=request.category,
        score=request.score
    )
    
    return KnowledgeResponse.model_validate(item)


@router.get("/categories/list")
async def get_knowledge_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """获取知识库所有分类"""
    cats = await knowledge_service.get_categories(db)
    return {"categories": cats}


@router.delete("/by-category/{category}", status_code=status.HTTP_200_OK)
async def delete_knowledge_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    删除指定分类下的所有知识条目

    - 需要管理员权限
    - 自动同步向量索引
    """
    count = await knowledge_service.delete_by_category(db, category)
    return {"deleted_count": count, "category": category}


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    获取知识条目详情
    
    - 需要管理员权限
    """
    item = await knowledge_service.get_knowledge(db, knowledge_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在"
        )
    
    return KnowledgeResponse.model_validate(item)


@router.put("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: str,
    request: UpdateKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    更新知识条目
    
    - 需要管理员权限
    - 自动检查重复（如果更新问题）
    - 自动同步向量索引
    """
    # 检查是否存在
    existing = await knowledge_service.get_knowledge(db, knowledge_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在"
        )
    
    # 如果更新问题，检查重复
    if request.question and request.question != existing.question:
        duplicate = await knowledge_service.check_duplicate(
            db, request.question, exclude_id=knowledge_id
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="知识条目已存在（问题重复）"
            )
    
    item = await knowledge_service.update_knowledge(
        db=db,
        knowledge_id=knowledge_id,
        question=request.question,
        answer=request.answer,
        keywords=request.keywords,
        category=request.category,
        score=request.score
    )
    
    return KnowledgeResponse.model_validate(item)


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    删除知识条目
    
    - 需要管理员权限
    - 自动同步向量索引
    """
    success = await knowledge_service.delete_knowledge(db, knowledge_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在"
        )
    
    return None


# ==================== 导入导出 ====================


@router.post("/import", response_model=ImportKnowledgeResponse)
async def import_knowledge(
    request: ImportKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    批量导入知识条目
    
    - 需要管理员权限
    - 支持跳过重复项
    """
    success_count, skip_count, errors = await knowledge_service.import_items(
        db=db,
        items=[item.model_dump() for item in request.items],
        skip_duplicates=request.skip_duplicates
    )
    
    return ImportKnowledgeResponse(
        success_count=success_count,
        skip_count=skip_count,
        errors=errors
    )


@router.get("/export/all", response_model=ExportKnowledgeResponse)
async def export_knowledge(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    导出所有知识条目
    
    - 需要管理员权限
    """
    items = await knowledge_service.export_all(db)
    
    return ExportKnowledgeResponse(
        items=items,
        total=len(items)
    )


# ==================== 向量索引管理 ====================

@router.get("/index/status", response_model=IndexStatusResponse)
async def get_index_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    获取向量索引状态
    
    - 需要管理员权限
    - 从数据库读取Embedding配置状态
    """
    from app.services.settings_service import SettingsService
    
    # 从数据库获取Embedding配置
    embedding_config = await SettingsService.get_embedding_config(db)
    
    # 同步配置到EmbeddingClient，确保状态一致
    await knowledge_service.vector_service.sync_config_from_db(db)
    
    # 检查Embedding是否已配置（有API key）
    embedding_available = bool(embedding_config.api_key)
    if not embedding_available:
        # 也检查LLM的API key作为后备
        llm_config = await SettingsService.get_llm_config(db)
        embedding_available = bool(llm_config.api_key)
    
    # 获取向量索引基本状态
    status_info = knowledge_service.get_index_status()
    needs_rebuild, rebuild_reason = knowledge_service.check_index_needs_rebuild()
    
    return IndexStatusResponse(
        count=status_info["count"],
        dimension=status_info["dimension"],
        embedding_model=embedding_config.model if embedding_available else None,
        embedding_available=embedding_available,
        embedding_dimension=embedding_config.dimension if embedding_available else None,
        needs_rebuild=needs_rebuild,
        rebuild_reason=rebuild_reason if needs_rebuild else None
    )


@router.post("/index/rebuild")
async def rebuild_index(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    重建向量索引（SSE 流式进度）

    - 需要管理员权限
    - 会先从数据库同步Embedding配置
    - 然后清空现有索引并重新构建
    - 返回 SSE 事件流
    """
    from sqlalchemy import select
    from app.models.knowledge import KnowledgeItem as KBModel

    # 预加载配置 & 清空索引
    config_ok = await knowledge_service.vector_service.sync_config_from_db(db)
    if not config_ok and not knowledge_service.vector_service.is_embedding_available():
        # 直接返回错误 SSE
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Embedding服务不可用：未配置API密钥'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    # 从数据库同步 chunk 配置到运行时 Config
    from app.services.settings_service import SettingsService
    from app.core.config import Config as RuntimeConfig
    rag_cfg = await SettingsService.get_rag_config(db)
    _rt = RuntimeConfig()
    _rt.set("chunk_size", rag_cfg.chunk_size)
    _rt.set("chunk_overlap", rag_cfg.chunk_overlap)

    await knowledge_service.vector_service.clear()

    result = await db.execute(select(KBModel))
    items = list(result.scalars().all())
    total = len(items)

    async def event_stream():
        success_count = 0
        fail_count = 0

        yield f"data: {json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

        for idx, item in enumerate(items):
            current = idx + 1
            try:
                ok = await knowledge_service._sync_vector_add(item, persist_index=False)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1

            yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total}, ensure_ascii=False)}\n\n"

        await knowledge_service.vector_service.save()

        yield f"data: {json.dumps({'type': 'done', 'success_count': success_count, 'fail_count': fail_count, 'total': total}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

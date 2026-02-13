# -*- coding: utf-8 -*-
"""
对话API - RAG调试
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.knowledge_service import KnowledgeService
from app.schemas.chat import DebugRAGRequest, DebugRAGResponse, DebugRAGItem
from app.api.dependencies import CSOrAdminRequired
from app.models.user import User
from app.api.chat.dependencies import get_rag_service


def register_debug_routes(router: APIRouter):
    """注册 RAG 调试路由到给定的 router"""

    @router.post("/debug-rag", response_model=DebugRAGResponse)
    async def debug_rag(
        request: DebugRAGRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(CSOrAdminRequired)
    ):
        """
        RAG检索调试
        
        - **query**: 查询内容
        
        Returns: RAG检索结果，包括改写后的查询、检索到的知识条目、上下文文本等
        """
        rag_service = await get_rag_service(db)
        
        # 获取知识库条目
        knowledge_items = await KnowledgeService.get_all_knowledge_items(db)
        
        if not knowledge_items:
            return DebugRAGResponse(
                query=request.query,
                rewritten_query=request.query,
                retrieved_items=[],
                context_text="",
                search_method="vector"
            )
        
        # 转换为RAG服务需要的格式
        items_for_rag = [
            {
                "id": item.id,
                "question": item.question,
                "answer": item.answer,
                "keywords": item.keywords or [],
                "category": item.category or "通用"
            }
            for item in knowledge_items
        ]
        
        try:
            # 执行RAG检索
            rag_result = await rag_service.search(request.query, items_for_rag)
            
            # 构建响应
            retrieved_items = [
                DebugRAGItem(
                    id=item.get("id", ""),
                    question=item.get("question", ""),
                    answer=item.get("answer", ""),
                    score=item.get("score", 0.0),
                    category=item.get("category", "通用")
                )
                for item in rag_result.retrieved_items
            ]
            
            return DebugRAGResponse(
                query=request.query,
                rewritten_query=rag_result.rewritten_query or request.query,
                retrieved_items=retrieved_items,
                context_text=rag_result.context_text or "",
                search_method=rag_result.search_method or "vector"
            )
        except Exception as e:
            # 如果RAG服务失败，返回空结果
            return DebugRAGResponse(
                query=request.query,
                rewritten_query=request.query,
                retrieved_items=[],
                context_text=f"RAG检索失败: {str(e)}",
                search_method="vector"
            )

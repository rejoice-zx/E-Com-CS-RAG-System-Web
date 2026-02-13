# -*- coding: utf-8 -*-
"""
对话API - 消息管理
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.services.chat_service import ChatService
from app.schemas.chat import (
    MessageResponse,
    MessageListResponse,
)
from app.api.chat.dependencies import get_authorized_conversation, require_chat_customer_id
from app.api.dependencies import AdminRequired, get_optional_user
from app.models.conversation import Conversation
from app.models.user import User


def _is_staff(current_user: Optional[User]) -> bool:
    return bool(current_user and current_user.role in ("admin", "cs"))


def register_message_routes(router: APIRouter):
    """注册消息管理路由到给定的 router"""

    @router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
    async def get_messages(
        conversation: Conversation = Depends(get_authorized_conversation),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        include_deleted: bool = Query(False, description="是否包含用户已删除消息（仅管理员/客服）"),
        since_id: Optional[int] = Query(None, description="增量拉取：仅返回 id > since_id 的消息"),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
    ):
        """
        获取对话消息（分页）
        
        - **conversation_id**: 对话ID
        - **page**: 页码（从1开始）
        - **page_size**: 每页数量（1-100）
        - **since_id**: 增量拉取，仅返回 id 大于此值的消息（忽略分页参数）
        
        Returns: 消息列表和分页信息
        """
        # 仅管理员/客服允许查看用户软删除消息
        effective_include_deleted = include_deleted and _is_staff(current_user)
        messages, total = await ChatService.get_messages(
            db,
            conversation.id,
            page=page,
            page_size=page_size,
            include_deleted=effective_include_deleted,
            since_id=since_id,
        )
        
        items = [
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                confidence=msg.confidence,
                rag_trace=msg.rag_trace,
                human_agent_name=msg.human_agent_name,
                is_deleted_by_user=msg.is_deleted_by_user,
                deleted_by_customer_id=msg.deleted_by_customer_id,
                deleted_at=msg.deleted_at,
                timestamp=msg.timestamp
            )
            for msg in messages
        ]
        
        return MessageListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size
        )

    @router.delete("/conversations/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_message(
        message_id: int,
        conversation: Conversation = Depends(get_authorized_conversation),
        hard: bool = Query(False, description="管理员是否执行最终删除"),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
        customer_id: str = Depends(require_chat_customer_id),
    ):
        """
        删除单条消息：
        - 普通用户：软删除（仅自己不可见）
        - admin/cs：可通过 hard=true 执行最终删除（物理删除）
        """
        message = await ChatService.get_message(db, message_id)
        if not message or message.conversation_id != conversation.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在",
            )

        is_staff = _is_staff(current_user)
        if hard:
            if not is_staff:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="仅管理员或客服可执行最终删除",
                )
            await ChatService.hard_delete_message(db, message)
            return

        # 软删除必须是会话拥有者（管理员/客服不执行软删除）
        if is_staff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="管理员请使用 hard=true 执行最终删除",
            )

        await ChatService.soft_delete_message_by_user(db, message, deleted_by_customer_id=customer_id)

    @router.get("/messages/count-by-date", response_model=dict)
    async def count_messages_by_date(
        before: Optional[datetime] = Query(None, description="删除此时间之前的消息 (ISO格式)"),
        after: Optional[datetime] = Query(None, description="删除此时间之后的消息 (ISO格式)"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(AdminRequired),
    ):
        """统计指定日期范围内的消息数量（仅管理员）"""
        if not before and not after:
            raise HTTPException(status_code=400, detail="至少需要提供 before 或 after 参数")
        count = await ChatService.count_messages_by_date_range(db, before=before, after=after)
        return {"count": count}

    @router.delete("/messages/batch-by-date", status_code=status.HTTP_200_OK)
    async def batch_delete_messages_by_date(
        before: Optional[datetime] = Query(None, description="删除此时间之前的消息 (ISO格式)"),
        after: Optional[datetime] = Query(None, description="删除此时间之后的消息 (ISO格式)"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(AdminRequired),
    ):
        """按日期范围批量物理删除消息（仅管理员）"""
        if not before and not after:
            raise HTTPException(status_code=400, detail="至少需要提供 before 或 after 参数")
        count = await ChatService.batch_delete_messages_by_date_range(db, before=before, after=after)
        return {"deleted_count": count, "message": f"已删除 {count} 条消息"}

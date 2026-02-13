# -*- coding: utf-8 -*-
"""Conversation APIs."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.dependencies import get_authorized_conversation
from app.api.dependencies import AdminRequired, get_customer_id_from_token, get_optional_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.chat import (
    ConversationListResponse,
    ConversationResponse,
    ConversationSummary,
    CreateConversationRequest,
    UpdateConversationRequest,
)
from app.services.chat_service import ChatService


def register_conversation_routes(router: APIRouter):
    """Register conversation CRUD routes."""

    @router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
    async def create_conversation(
        request: CreateConversationRequest = None,
        db: AsyncSession = Depends(get_db),
        customer_id: Optional[str] = Depends(get_customer_id_from_token),
        x_device_id: Optional[str] = Header(None, alias="X-Device-ID"),
        x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    ):
        """Create a conversation for current token owner."""
        title = request.title if request and request.title else "新对话"

        effective_customer_id = customer_id or "anonymous"
        guest_session_id = None
        guest_device_id = None
        if effective_customer_id.startswith("visitor_"):
            guest_session_id = x_session_id or effective_customer_id
            guest_device_id = x_device_id

        conversation = await ChatService.create_conversation(
            db,
            title=title,
            customer_id=effective_customer_id,
            temp_session_id=guest_session_id,
            temp_device_id=guest_device_id,
        )

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            customer_id=conversation.customer_id,
            human_agent_id=conversation.human_agent_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=0,
        )

    @router.get("/conversations", response_model=ConversationListResponse)
    async def get_conversations(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        status_filter: Optional[str] = Query(None, alias="status", description="状态过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
        customer_id: Optional[str] = Depends(get_customer_id_from_token),
    ):
        """List conversations in permission scope."""
        effective_customer_id = None
        if current_user and current_user.role in ("admin", "cs"):
            effective_customer_id = None
        elif customer_id:
            effective_customer_id = customer_id
        elif current_user:
            effective_customer_id = f"user_{current_user.id}"
        else:
            effective_customer_id = "anonymous"

        conversations, total = await ChatService.get_conversations(
            db,
            page=page,
            page_size=page_size,
            customer_id=effective_customer_id,
            status=status_filter,
            include_deleted=bool(current_user and current_user.role in ("admin", "cs")),
        )

        include_deleted = bool(current_user and current_user.role in ("admin", "cs"))
        conversation_ids = [conv.id for conv in conversations]
        message_counts = await ChatService.get_message_counts_for_conversations(
            db,
            conversation_ids,
            include_deleted=include_deleted,
        )
        items = []
        for conv in conversations:
            items.append(
                ConversationSummary(
                    id=conv.id,
                    title=conv.title,
                    status=conv.status,
                    customer_id=conv.customer_id,
                    updated_at=conv.updated_at,
                    message_count=message_counts.get(conv.id, 0),
                )
            )

        return ConversationListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    @router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
    async def get_conversation(
        conversation: Conversation = Depends(get_authorized_conversation),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
    ):
        """Get conversation detail."""
        include_deleted = bool(current_user and current_user.role in ("admin", "cs"))
        msg_count = await ChatService.get_message_count(
            db,
            conversation.id,
            include_deleted=include_deleted,
        )

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            customer_id=conversation.customer_id,
            human_agent_id=conversation.human_agent_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=msg_count,
        )

    @router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
    async def update_conversation(
        request: UpdateConversationRequest,
        conversation: Conversation = Depends(get_authorized_conversation),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
    ):
        """Update conversation metadata."""
        conversation = await ChatService.update_conversation(
            db,
            conversation.id,
            title=request.title,
            status=request.status,
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在",
            )

        include_deleted = bool(current_user and current_user.role in ("admin", "cs"))
        msg_count = await ChatService.get_message_count(
            db,
            conversation.id,
            include_deleted=include_deleted,
        )

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            customer_id=conversation.customer_id,
            human_agent_id=conversation.human_agent_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=msg_count,
        )

    @router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_conversation(
        conversation: Conversation = Depends(get_authorized_conversation),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_user),
        customer_id: Optional[str] = Depends(get_customer_id_from_token),
    ):
        """
        删除单个对话：
        - 普通用户/访客：软删除（用户视角隐藏，管理员仍可在工作台查看）
        - admin/cs：物理删除（级联删除所有消息）
        """
        is_staff = bool(current_user and current_user.role in ("admin", "cs"))

        if is_staff:
            success = await ChatService.hard_delete_conversation(db, conversation.id)
        else:
            success = await ChatService.delete_conversation(
                db, conversation.id, deleted_by_customer_id=customer_id,
            )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在",
            )

    @router.delete("/conversations", status_code=status.HTTP_200_OK)
    async def delete_all_conversations(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(AdminRequired),
    ):
        """Delete all conversations (admin only)."""
        count = await ChatService.delete_all_conversations(db)
        return {"deleted_count": count, "message": f"已删除 {count} 个对话"}

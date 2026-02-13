# -*- coding: utf-8 -*-
"""
人工客服API端点 - Human Service API Endpoints

功能:
- 获取待处理对话列表
- 接入对话
- 关闭人工服务
- 发送人工消息
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timezone

from app.database import get_db
from app.services.human_service import HumanService, HumanServiceError, ConversationStatus
from app.services.chat_service import ChatService
from app.services.ws_manager import ws_manager
from app.schemas.human import (
    PendingConversationSummary,
    PendingConversationListResponse,
    HandlingConversationSummary,
    HandlingConversationListResponse,
    AcceptConversationResponse,
    CloseServiceResponse,
    SendHumanMessageRequest,
    HumanMessageResponse,
    CancelTransferResponse,
    ReturnToAIResponse
)
from app.api.dependencies import CSOrAdminRequired
from app.models.user import User
from app.utils.time import utcnow

from app.api.human_ws import register_human_ws_routes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/human", tags=["Human Service"])

# 注册WebSocket路由
register_human_ws_routes(router)


# ==================== 待处理对话管理 ====================

@router.get("/pending", response_model=PendingConversationListResponse)
async def get_pending_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    获取待处理对话列表
    
    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（1-100）
    
    Returns: 待处理对话列表和分页信息
    """
    conversations, total = await HumanService.get_pending_conversations(
        db, page=page, page_size=page_size
    )
    
    now = utcnow()
    items = []
    for conv in conversations:
        msg_count = await ChatService.get_message_count(db, conv.id)
        # 计算等待时间 - 确保时区一致
        wait_seconds = 0
        if conv.updated_at:
            updated_at = conv.updated_at
            # 如果updated_at是naive datetime，添加UTC时区
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            wait_seconds = int((now - updated_at).total_seconds())
        items.append(PendingConversationSummary(
            id=conv.id,
            title=conv.title,
            status=conv.status,
            customer_id=conv.customer_id,
            updated_at=conv.updated_at,
            message_count=msg_count,
            wait_time_seconds=wait_seconds
        ))
    
    return PendingConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )



@router.get("/handling", response_model=HandlingConversationListResponse)
async def get_handling_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    获取当前客服正在处理的对话列表
    
    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（1-100）
    
    Returns: 正在处理的对话列表和分页信息
    """
    # 管理员可以查看所有处理中的对话，客服只能看自己的
    agent_filter = None if current_user.role == "admin" else current_user.id
    conversations, total = await HumanService.get_handling_conversations(
        db, agent_id=agent_filter, page=page, page_size=page_size
    )
    
    items = []
    for conv in conversations:
        msg_count = await ChatService.get_message_count(db, conv.id)
        items.append(HandlingConversationSummary(
            id=conv.id,
            title=conv.title,
            status=conv.status,
            customer_id=conv.customer_id,
            human_agent_id=conv.human_agent_id,
            updated_at=conv.updated_at,
            message_count=msg_count
        ))
    
    return HandlingConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


# ==================== 对话接入与关闭 ====================

@router.post("/accept/{conversation_id}", response_model=AcceptConversationResponse)
async def accept_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    接入对话
    
    - **conversation_id**: 对话ID
    
    Returns: 接入结果
    """
    try:
        conversation = await HumanService.accept_conversation(
            db, conversation_id, current_user.id
        )
        
        # 查询系统消息（accept_conversation 写入的"人工客服已接入"）
        from sqlalchemy import select as sa_select
        from app.models.conversation import Message as MsgModel
        latest_stmt = (
            sa_select(MsgModel)
            .where(MsgModel.conversation_id == conversation_id)
            .order_by(MsgModel.timestamp.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        accept_msg = latest_result.scalar_one_or_none()

        sys_msg = None
        if accept_msg:
            sys_msg = {
                "id": accept_msg.id,
                "role": accept_msg.role,
                "content": accept_msg.content,
                "timestamp": accept_msg.timestamp.isoformat(),
            }

        # 统一广播状态变更（客户 + 对话级客服 + 全局客服）
        await ws_manager.publish_status_change(
            conversation_id=conversation_id,
            customer_id=conversation.customer_id,
            new_status=conversation.status,
            message="人工客服已接入",
            extra={"agent_id": current_user.id},
            system_message=sys_msg,
        )
        
        return AcceptConversationResponse(
            success=True,
            message="已成功接入对话",
            conversation_id=conversation.id,
            status=conversation.status,
            agent_id=current_user.id
        )
    except HumanServiceError as e:
        if e.code == "CONVERSATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        elif e.code == "INVALID_STATUS_TRANSITION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message
            )


@router.post("/close/{conversation_id}", response_model=CloseServiceResponse)
async def close_human_service(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    关闭人工服务
    
    - **conversation_id**: 对话ID
    
    Returns: 关闭结果
    """
    try:
        conversation = await HumanService.close_human_service(
            db, conversation_id, current_user.id
        )
        
        # 查询系统消息（close_human_service 写入的关闭提示）
        from sqlalchemy import select as sa_select
        from app.models.conversation import Message as MsgModel
        latest_stmt = (
            sa_select(MsgModel)
            .where(MsgModel.conversation_id == conversation_id)
            .order_by(MsgModel.timestamp.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        close_msg = latest_result.scalar_one_or_none()

        sys_msg = None
        if close_msg:
            sys_msg = {
                "id": close_msg.id,
                "role": close_msg.role,
                "content": close_msg.content,
                "timestamp": close_msg.timestamp.isoformat(),
            }

        # 统一广播状态变更（客户 + 对话级客服 + 全局客服）
        await ws_manager.publish_status_change(
            conversation_id=conversation_id,
            customer_id=conversation.customer_id,
            new_status=conversation.status,
            message="人工服务已关闭",
            system_message=sys_msg,
        )
        
        return CloseServiceResponse(
            success=True,
            message="人工服务已关闭",
            conversation_id=conversation.id,
            status=conversation.status
        )
    except HumanServiceError as e:
        if e.code == "CONVERSATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        elif e.code in ("INVALID_STATUS_TRANSITION", "NOT_CURRENT_AGENT"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message
            )



# ==================== 消息发送 ====================

@router.post("/{conversation_id}/messages", response_model=HumanMessageResponse)
async def send_human_message(
    conversation_id: str,
    request: SendHumanMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    客服发送消息
    
    - **conversation_id**: 对话ID
    - **content**: 消息内容
    
    Returns: 发送的消息
    """
    try:
        message = await HumanService.send_human_message(
            db, conversation_id, current_user.id, request.content
        )
        
        # 通过 ws_manager 推送给客户
        conversation = await ChatService.get_conversation(db, conversation_id)
        if conversation and conversation.customer_id:
            await ws_manager.send_to_customer(conversation.customer_id, {
                "type": "message",
                "id": message.id,
                "conversation_id": conversation_id,
                "role": "human",
                "content": message.content,
                "human_agent_name": message.human_agent_name,
                "timestamp": message.timestamp.isoformat(),
            })

        # 通知所有客服全局通道：该对话有新消息
        await ws_manager.broadcast_to_all_agents({
            "type": "new_message",
            "conversation_id": conversation_id,
            "message": {
                "id": message.id,
                "role": "human",
                "content": message.content,
                "human_agent_name": message.human_agent_name,
                "timestamp": message.timestamp.isoformat(),
            },
        })
        
        return HumanMessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            timestamp=message.timestamp
        )
    except HumanServiceError as e:
        if e.code == "CONVERSATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        elif e.code in ("INVALID_STATUS", "NOT_CURRENT_AGENT"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message
            )


# ==================== 取消转人工 ====================

@router.post("/cancel/{conversation_id}", response_model=CancelTransferResponse)
async def cancel_transfer(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    取消转人工请求
    
    - **conversation_id**: 对话ID
    
    Returns: 取消结果
    """
    try:
        conversation = await HumanService.cancel_transfer(db, conversation_id)
        
        # 查询系统消息（cancel_transfer 写入的"转人工请求已取消"）
        from sqlalchemy import select as sa_select
        from app.models.conversation import Message as MsgModel
        latest_stmt = (
            sa_select(MsgModel)
            .where(MsgModel.conversation_id == conversation_id)
            .order_by(MsgModel.timestamp.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        cancel_msg = latest_result.scalar_one_or_none()

        sys_msg = None
        if cancel_msg:
            sys_msg = {
                "id": cancel_msg.id,
                "role": cancel_msg.role,
                "content": cancel_msg.content,
                "timestamp": cancel_msg.timestamp.isoformat(),
            }

        # 统一广播状态变更（客户 + 对话级客服 + 全局客服）
        await ws_manager.publish_status_change(
            conversation_id=conversation_id,
            customer_id=conversation.customer_id,
            new_status=conversation.status,
            message="转人工请求已取消",
            system_message=sys_msg,
        )
        
        return CancelTransferResponse(
            success=True,
            message="已取消转人工请求",
            conversation_id=conversation.id,
            status=conversation.status
        )
    except HumanServiceError as e:
        if e.code == "CONVERSATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        elif e.code == "INVALID_STATUS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message
            )


# ==================== 返回AI模式 ====================

@router.post("/return-ai/{conversation_id}", response_model=ReturnToAIResponse)
async def return_to_ai(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    将对话返回AI模式（从human_closed状态）
    
    - **conversation_id**: 对话ID
    
    Returns: 返回结果
    """
    try:
        conversation = await HumanService.return_to_ai(db, conversation_id)
        
        # 统一广播状态变更（客户 + 对话级客服 + 全局客服）
        await ws_manager.publish_status_change(
            conversation_id=conversation_id,
            customer_id=conversation.customer_id,
            new_status=conversation.status,
            message="对话已返回AI模式",
        )
        
        return ReturnToAIResponse(
            success=True,
            message="对话已返回AI模式",
            conversation_id=conversation.id,
            status=conversation.status
        )
    except HumanServiceError as e:
        if e.code == "CONVERSATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
        elif e.code == "INVALID_STATUS_TRANSITION":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message
            )


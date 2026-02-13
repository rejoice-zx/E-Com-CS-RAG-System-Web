# -*- coding: utf-8 -*-
"""
对话API - 转人工客服
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.chat_service import ChatService
from app.services.ws_manager import ws_manager
from app.schemas.chat import (
    TransferHumanRequest,
    TransferHumanResponse,
)
from app.api.chat.dependencies import get_authorized_conversation
from app.models.conversation import Conversation


def register_transfer_routes(router: APIRouter):
    """注册转人工路由到给定的 router"""

    @router.post("/conversations/{conversation_id}/transfer-human", response_model=TransferHumanResponse)
    async def transfer_to_human(
        conversation: Conversation = Depends(get_authorized_conversation),
        request: TransferHumanRequest = None,
        db: AsyncSession = Depends(get_db),
    ):
        """
        转人工客服
        
        - **conversation_id**: 对话ID
        - **reason**: 转人工原因（可选）
        
        Returns: 转人工结果
        """
        # 检查当前状态是否允许转人工
        if conversation.status != "normal":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"当前对话状态({conversation.status})不允许转人工"
            )
        
        # 更新状态为等待人工接入
        conversation = await ChatService.update_conversation(
            db, conversation.id, status="pending_human"
        )
        
        # 添加系统消息
        reason_text = f"（原因：{request.reason}）" if request and request.reason else ""
        system_msg = await ChatService.add_message(
            db,
            conversation.id,
            role="assistant",
            content=f"您的对话已转接人工客服{reason_text}，请稍候..."
        )

        # 推送系统消息给客户
        sys_msg = None
        if system_msg:
            sys_msg = {
                "id": system_msg.id,
                "role": "assistant",
                "content": system_msg.content,
                "timestamp": system_msg.timestamp.isoformat(),
            }

        # 统一广播状态变更（客户 + 对话级客服 + 全局客服）
        await ws_manager.publish_status_change(
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            new_status="pending_human",
            message="已转接人工客服，请稍候",
            system_message=sys_msg,
        )

        # 额外通知所有在线客服：有新的待处理对话（含标题等元信息）
        await ws_manager.broadcast_to_all_agents({
            "type": "new_pending",
            "conversation_id": conversation.id,
            "title": conversation.title,
            "customer_id": conversation.customer_id,
        })
        
        return TransferHumanResponse(
            success=True,
            message="已转接人工客服，请稍候",
            conversation_id=conversation.id,
            status="pending_human"
        )

# -*- coding: utf-8 -*-
"""
人工客服WebSocket端点 - Human Service WebSocket Endpoints

功能:
- WebSocket实时通信
- 令牌验证
- 消息收发
"""

import logging
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.human_service import HumanService, HumanServiceError, ConversationStatus
from app.services.chat_service import ChatService
from app.services.ws_manager import ws_manager
from app.models.user import User

logger = logging.getLogger(__name__)


async def verify_websocket_token(websocket: WebSocket, db: AsyncSession) -> User:
    """
    验证WebSocket连接的JWT令牌

    Args:
        websocket: WebSocket连接
        db: 数据库会话

    Returns:
        验证通过的用户对象

    Raises:
        WebSocketDisconnect: 如果验证失败
    """
    from app.services.auth_service import AuthService

    # 从查询参数获取令牌
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001, reason="缺少认证令牌")
        raise WebSocketDisconnect(code=4001)

    # 验证令牌
    payload = AuthService.verify_token(token, token_type="access")

    if not payload:
        await websocket.close(code=4001, reason="无效或过期的令牌")
        raise WebSocketDisconnect(code=4001)

    # 获取用户
    user_id = int(payload.get("sub"))
    user = await AuthService.get_user_by_id(db, user_id)

    if not user or not user.is_active:
        await websocket.close(code=4001, reason="用户不存在或已禁用")
        raise WebSocketDisconnect(code=4001)

    # 检查角色权限
    if user.role not in ("admin", "cs"):
        await websocket.close(code=4003, reason="权限不足")
        raise WebSocketDisconnect(code=4003)

    return user


def register_human_ws_routes(router: APIRouter):
    """注册人工客服WebSocket路由到给定的 router"""

    @router.websocket("/ws")
    async def agent_global_websocket(
        websocket: WebSocket,
        db: AsyncSession = Depends(get_db)
    ):
        """
        客服全局WebSocket端点 - 接收跨对话事件通知

        连接URL: ws://host/api/human/ws?token={jwt_token}

        服务端推送事件:
        - {"type": "new_pending", "conversation_id": "...", "title": "...", "customer_id": "..."}
        - {"type": "new_message", "conversation_id": "...", "message": {...}}
        - {"type": "status_change", "conversation_id": "...", "status": "...", "message": "..."}
        - {"type": "pong"}
        - {"type": "connected", "user_id": ...}
        """
        try:
            user = await verify_websocket_token(websocket, db)
        except WebSocketDisconnect:
            return

        await ws_manager.connect_agent_global(websocket, user.id)

        await ws_manager.send_to_ws(websocket, {
            "type": "connected",
            "user_id": user.id,
        })

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")
                if msg_type == "ping":
                    await ws_manager.send_to_ws(websocket, {"type": "pong"})
                else:
                    await ws_manager.send_to_ws(websocket, {
                        "type": "error",
                        "message": f"全局通道不支持发送消息类型: {msg_type}"
                    })
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            ws_manager.disconnect(websocket)
            logger.error(f"Agent global WebSocket error: {e}")

    @router.websocket("/ws/{conversation_id}")
    async def websocket_endpoint(
        websocket: WebSocket,
        conversation_id: str,
        db: AsyncSession = Depends(get_db)
    ):
        """
        WebSocket实时通信端点

        连接URL: ws://host/api/human/ws/{conversation_id}?token={jwt_token}

        消息格式:
        - 发送消息: {"type": "message", "content": "消息内容"}
        - 接收消息: {"type": "message", "id": 123, "role": "human/user", "content": "...", "timestamp": "..."}
        - 状态更新: {"type": "status", "status": "human_handling/human_closed", "agent_id": 123}
        - 错误: {"type": "error", "message": "错误信息"}
        - 心跳: {"type": "ping"} -> {"type": "pong"}
        """
        # 验证令牌
        try:
            user = await verify_websocket_token(websocket, db)
        except WebSocketDisconnect:
            return

        # 验证对话存在且状态正确
        conversation = await HumanService.get_conversation_with_messages(db, conversation_id)

        if not conversation:
            await websocket.close(code=4004, reason="对话不存在")
            return

        # 检查对话状态是否允许WebSocket连接
        allowed_statuses = [
            ConversationStatus.PENDING_HUMAN,
            ConversationStatus.HUMAN_HANDLING
        ]

        if conversation.status not in allowed_statuses:
            await websocket.close(code=4000, reason=f"对话状态({conversation.status})不支持实时通信")
            return

        # 如果是human_handling状态，检查是否是当前处理的客服
        if conversation.status == ConversationStatus.HUMAN_HANDLING:
            if conversation.human_agent_id != user.id:
                await websocket.close(code=4003, reason="只有当前处理的客服才能连接")
                return

        # 建立连接（统一使用 ws_manager）
        await ws_manager.connect_agent(websocket, conversation_id, user.id)

        # 发送连接成功消息
        await ws_manager.send_to_ws(websocket, {
            "type": "connected",
            "conversation_id": conversation_id,
            "user_id": user.id,
            "status": conversation.status,
            "connection_count": ws_manager.get_conversation_connection_count(conversation_id)
        })

        try:
            while True:
                # 接收消息
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "ping":
                    # 心跳响应
                    await ws_manager.send_to_ws(websocket, {"type": "pong"})

                elif msg_type == "message":
                    # 发送消息
                    content = data.get("content", "").strip()

                    if not content:
                        await ws_manager.send_to_ws(websocket, {
                            "type": "error",
                            "message": "消息内容不能为空"
                        })
                        continue

                    try:
                        # 保存消息
                        message = await HumanService.send_human_message(
                            db, conversation_id, user.id, content
                        )

                        msg_data = {
                            "type": "message",
                            "id": message.id,
                            "conversation_id": message.conversation_id,
                            "role": message.role,
                            "content": message.content,
                            "human_agent_name": message.human_agent_name,
                            "timestamp": message.timestamp.isoformat(),
                            "sender_id": user.id
                        }

                        # 广播消息给对话中的其他客服连接
                        await ws_manager.send_to_conversation_agents(
                            conversation_id, msg_data, exclude=websocket
                        )

                        # 推送给客户
                        conv = await ChatService.get_conversation(db, conversation_id)
                        if conv and conv.customer_id:
                            await ws_manager.send_to_customer(conv.customer_id, {
                                "type": "message",
                                "id": message.id,
                                "conversation_id": message.conversation_id,
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
                                "role": message.role,
                                "content": message.content,
                                "human_agent_name": message.human_agent_name,
                                "timestamp": message.timestamp.isoformat(),
                            },
                        })

                    except HumanServiceError as e:
                        await ws_manager.send_to_ws(websocket, {
                            "type": "error",
                            "message": e.message
                        })

                elif msg_type == "close":
                    # 关闭人工服务
                    try:
                        conversation = await HumanService.close_human_service(
                            db, conversation_id, user.id
                        )

                        # 查询系统消息
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

                    except HumanServiceError as e:
                        await ws_manager.send_to_ws(websocket, {
                            "type": "error",
                            "message": e.message
                        })

                else:
                    await ws_manager.send_to_ws(websocket, {
                        "type": "error",
                        "message": f"未知消息类型: {msg_type}"
                    })

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

            # 广播断开连接消息
            await ws_manager.send_to_conversation_agents(conversation_id, {
                "type": "disconnected",
                "user_id": user.id,
                "connection_count": ws_manager.get_conversation_connection_count(conversation_id)
            })

        except Exception as e:
            ws_manager.disconnect(websocket)
            logger.error(f"WebSocket错误: {e}")

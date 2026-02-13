# -*- coding: utf-8 -*-
"""
对话API - 客户WebSocket端点
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.database import get_db
from app.services.chat_service import ChatService
from app.services.ws_manager import ws_manager
from app.services.statistics_service import StatisticsService


logger = logging.getLogger(__name__)


def register_websocket_routes(router: APIRouter):
    """注册客户 WebSocket 路由到给定的 router"""

    @router.websocket("/ws")
    async def customer_websocket(
        websocket: WebSocket,
        db: AsyncSession = Depends(get_db),
    ):
        """
        客户端 WebSocket 端点

        连接URL: ws://host/api/chat/ws?token={jwt_token}

        支持 guest token 和 user token。
        客户连接后，服务端会推送该客户所有对话的新消息和状态变更。

        客户端发送:
        - {"type": "ping"}  -> 心跳
        - {"type": "message", "conversation_id": "xxx", "content": "xxx"}  -> 发送消息

        服务端推送:
        - {"type": "pong"}
        - {"type": "message", ...}  -> 新消息
        - {"type": "status", "conversation_id": "xxx", "status": "xxx"}  -> 状态变更
        - {"type": "connected", "customer_id": "xxx"}
        - {"type": "error", "message": "xxx"}
        """
        from app.services.auth_service import AuthService

        # 从查询参数获取 token
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="缺少认证令牌")
            return

        payload = AuthService.verify_token(token, token_type="access")
        if not payload:
            await websocket.close(code=4001, reason="无效或过期的令牌")
            return

        sub = payload.get("sub", "")
        role = payload.get("role", "")

        # 确定 customer_id
        if role == "guest":
            customer_id = sub  # visitor_xxx
        else:
            customer_id = f"user_{sub}"

        # 建立连接
        await ws_manager.connect_customer(websocket, customer_id)

        await ws_manager.send_to_ws(websocket, {
            "type": "connected",
            "customer_id": customer_id,
        })

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "ping":
                    await ws_manager.send_to_ws(websocket, {"type": "pong"})

                elif msg_type == "message":
                    # 客户在人工对话中发送消息
                    conv_id = data.get("conversation_id", "")
                    content = data.get("content", "").strip()
                    if not conv_id or not content:
                        await ws_manager.send_to_ws(websocket, {"type": "error", "message": "缺少 conversation_id 或 content"})
                        continue

                    conversation = await ChatService.get_conversation(db, conv_id)
                    if not conversation or conversation.customer_id != customer_id:
                        await ws_manager.send_to_ws(websocket, {"type": "error", "message": "对话不存在"})
                        continue

                    if conversation.status == "human_handling":
                        # 保存用户消息
                        user_msg = await ChatService.add_message(db, conv_id, role="user", content=content)
                        StatisticsService.record_question(content)
                        if user_msg:
                            msg_data = {
                                "type": "message",
                                "id": user_msg.id,
                                "conversation_id": conv_id,
                                "role": "user",
                                "content": content,
                                "timestamp": user_msg.timestamp.isoformat(),
                            }
                            # 推送给对话中的客服
                            await ws_manager.send_to_conversation_agents(conv_id, msg_data)
                            # 也推送给客户自己（确认）
                            await ws_manager.send_to_ws(websocket, msg_data)
                            # 通知所有客服全局通道：该对话有新客户消息
                            await ws_manager.broadcast_to_all_agents({
                                "type": "new_message",
                                "conversation_id": conv_id,
                                "message": {
                                    "id": user_msg.id,
                                    "role": "user",
                                    "content": content,
                                    "timestamp": user_msg.timestamp.isoformat(),
                                },
                            })
                    else:
                        await ws_manager.send_to_ws(websocket, {"type": "error", "message": "当前对话状态不支持通过WebSocket发送消息"})

                else:
                    await ws_manager.send_to_ws(websocket, {"type": "error", "message": f"未知消息类型: {msg_type}"})

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            ws_manager.disconnect(websocket)
            logger.error(f"Customer WebSocket error: {e}")

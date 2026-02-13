# -*- coding: utf-8 -*-
"""
对话API端点 - Chat API Endpoints

功能:
- 对话CRUD操作
- 消息管理
- 转人工
- SSE流式响应
- 客户WebSocket
- RAG调试
"""

from fastapi import APIRouter

from app.api.chat.conversations import register_conversation_routes
from app.api.chat.messages import register_message_routes
from app.api.chat.transfer import register_transfer_routes
from app.api.chat.streaming import register_streaming_routes
from app.api.chat.websocket import register_websocket_routes
from app.api.chat.debug import register_debug_routes


router = APIRouter(prefix="/api/chat", tags=["Chat"])

# 注册所有子模块路由
register_conversation_routes(router)
register_message_routes(router)
register_transfer_routes(router)
register_streaming_routes(router)
register_websocket_routes(router)
register_debug_routes(router)

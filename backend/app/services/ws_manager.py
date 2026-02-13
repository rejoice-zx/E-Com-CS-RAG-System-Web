# -*- coding: utf-8 -*-
"""
WebSocket 连接管理器 - 统一管理所有 WebSocket 连接

支持三种连接维度:
- 按 conversation_id: 客服连接到特定对话
- 按 customer_id: 客户连接，接收所有自己对话的消息
- 按 agent user_id (全局): 客服全局连接，接收跨对话事件通知
"""

import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import WebSocket


class WSManager:
    """统一 WebSocket 连接管理器"""

    def __init__(self):
        # 按 conversation_id 分组 (客服端 - 对话级)
        # {conversation_id: {ws1, ws2, ...}}
        self._conv_connections: Dict[str, Set[WebSocket]] = {}

        # 按 customer_id 分组 (客户端)
        # {customer_id: {ws1, ws2, ...}}
        self._customer_connections: Dict[str, Set[WebSocket]] = {}

        # 按 agent user_id 分组 (客服端 - 全局)
        # {user_id: {ws1, ws2, ...}}
        self._agent_global_connections: Dict[int, Set[WebSocket]] = {}

        # ws -> 元信息
        self._ws_meta: Dict[WebSocket, dict] = {}

    # ── 连接管理 ──

    async def connect_agent(self, ws: WebSocket, conversation_id: str, user_id: int):
        """客服连接到某个对话"""
        await ws.accept()
        if conversation_id not in self._conv_connections:
            self._conv_connections[conversation_id] = set()
        self._conv_connections[conversation_id].add(ws)
        self._ws_meta[ws] = {"type": "agent", "conversation_id": conversation_id, "user_id": user_id}

    async def connect_customer(self, ws: WebSocket, customer_id: str):
        """客户连接（接收自己所有对话的消息）"""
        await ws.accept()
        if customer_id not in self._customer_connections:
            self._customer_connections[customer_id] = set()
        self._customer_connections[customer_id].add(ws)
        self._ws_meta[ws] = {"type": "customer", "customer_id": customer_id}

    async def connect_agent_global(self, ws: WebSocket, user_id: int):
        """客服全局连接（接收所有跨对话事件通知）"""
        await ws.accept()
        if user_id not in self._agent_global_connections:
            self._agent_global_connections[user_id] = set()
        self._agent_global_connections[user_id].add(ws)
        self._ws_meta[ws] = {"type": "agent_global", "user_id": user_id}

    def disconnect(self, ws: WebSocket):
        """断开连接（自动清理）"""
        meta = self._ws_meta.pop(ws, None)
        if not meta:
            return

        if meta["type"] == "agent":
            conv_id = meta["conversation_id"]
            if conv_id in self._conv_connections:
                self._conv_connections[conv_id].discard(ws)
                if not self._conv_connections[conv_id]:
                    del self._conv_connections[conv_id]

        elif meta["type"] == "customer":
            cid = meta["customer_id"]
            if cid in self._customer_connections:
                self._customer_connections[cid].discard(ws)
                if not self._customer_connections[cid]:
                    del self._customer_connections[cid]

        elif meta["type"] == "agent_global":
            uid = meta["user_id"]
            if uid in self._agent_global_connections:
                self._agent_global_connections[uid].discard(ws)
                if not self._agent_global_connections[uid]:
                    del self._agent_global_connections[uid]

    # ── 消息推送 ──

    async def _safe_send(self, ws: WebSocket, data: dict):
        """安全发送，失败时自动断开"""
        try:
            await ws.send_json(data)
        except Exception:
            self.disconnect(ws)

    async def send_to_customer(self, customer_id: str, data: dict):
        """向某个客户的所有连接推送消息"""
        connections = self._customer_connections.get(customer_id, set()).copy()
        for ws in connections:
            await self._safe_send(ws, data)

    async def send_to_conversation_agents(self, conversation_id: str, data: dict, exclude: Optional[WebSocket] = None):
        """向某个对话的所有客服连接推送消息"""
        connections = self._conv_connections.get(conversation_id, set()).copy()
        for ws in connections:
            if ws != exclude:
                await self._safe_send(ws, data)

    async def broadcast_message(self, conversation_id: str, customer_id: str, data: dict, exclude: Optional[WebSocket] = None):
        """
        广播消息到对话的所有参与方:
        - 对话中的客服连接
        - 客户的连接
        """
        await self.send_to_conversation_agents(conversation_id, data, exclude=exclude)
        await self.send_to_customer(customer_id, data)

    async def send_to_ws(self, ws: WebSocket, data: dict):
        """向单个连接发送消息"""
        await self._safe_send(ws, data)

    async def send_to_agent(self, user_id: int, data: dict):
        """向某个客服的所有全局连接推送事件"""
        connections = self._agent_global_connections.get(user_id, set()).copy()
        for ws in connections:
            await self._safe_send(ws, data)

    async def broadcast_to_all_agents(self, data: dict):
        """广播事件给所有在线客服的全局连接"""
        for uid, connections in list(self._agent_global_connections.items()):
            for ws in connections.copy():
                await self._safe_send(ws, data)

    async def publish_status_change(
        self,
        conversation_id: str,
        customer_id: str | None,
        new_status: str,
        message: str,
        *,
        extra: dict | None = None,
        system_message: dict | None = None,
    ):
        """
        统一状态变更事件发布器。

        所有对话状态转换都应通过此方法广播，确保三个维度的连接
        （客户端、对话级客服端、全局客服端）都能收到一致的事件。

        Args:
            conversation_id: 对话 ID
            customer_id: 客户 ID（为 None 时跳过客户推送）
            new_status: 变更后的状态
            message: 人类可读的状态描述
            extra: 附加到 status_change 事件的额外字段（如 agent_id）
            system_message: 如果有系统消息需要推送给客户，传入
                            {"id": ..., "role": ..., "content": ..., "timestamp": ...}
        """
        # ── 1. 推送给客户端 ──
        if customer_id:
            await self.send_to_customer(customer_id, {
                "type": "status",
                "conversation_id": conversation_id,
                "status": new_status,
                "message": message,
            })
            # 如果有系统消息，也推送给客户
            if system_message:
                await self.send_to_customer(customer_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    **system_message,
                })

        # ── 2. 推送给对话级客服连接 ──
        await self.send_to_conversation_agents(conversation_id, {
            "type": "status",
            "conversation_id": conversation_id,
            "status": new_status,
            "message": message,
        })

        # ── 3. 广播给所有客服全局连接 ──
        event = {
            "type": "status_change",
            "conversation_id": conversation_id,
            "status": new_status,
            "message": message,
        }
        if extra:
            event.update(extra)
        await self.broadcast_to_all_agents(event)


    # ── 查询 ──

    def get_meta(self, ws: WebSocket) -> Optional[dict]:
        return self._ws_meta.get(ws)

    def has_customer_connections(self, customer_id: str) -> bool:
        return bool(self._customer_connections.get(customer_id))

    def has_conversation_connections(self, conversation_id: str) -> bool:
        return bool(self._conv_connections.get(conversation_id))

    def get_conversation_connection_count(self, conversation_id: str) -> int:
        """获取对话的客服连接数"""
        return len(self._conv_connections.get(conversation_id, set()))


# 全局单例
ws_manager = WSManager()

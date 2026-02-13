# -*- coding: utf-8 -*-
"""
对话服务模块 - Chat Service

功能:
- 对话CRUD操作
- 消息管理
- 对话历史维护
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, delete, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, Message
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class ChatService:
    """对话服务类"""
    
    @staticmethod
    def generate_conversation_id() -> str:
        """生成唯一对话ID"""
        return str(uuid.uuid4())
    
    @staticmethod
    async def create_conversation(
        db: AsyncSession,
        title: Optional[str] = None,
        customer_id: Optional[str] = None,
        temp_session_id: Optional[str] = None,
        temp_device_id: Optional[str] = None,
    ) -> Conversation:
        """
        创建新对话
        
        Args:
            db: 数据库会话
            title: 对话标题（可选）
            customer_id: 客户标识（可选）
            temp_session_id: 本地访客会话ID（可选）
            temp_device_id: 本地访客设备ID（可选）
        
        Returns:
            新创建的对话对象
        """
        conversation_id = ChatService.generate_conversation_id()
        
        conversation = Conversation(
            id=conversation_id,
            title=title or "新对话",
            status="normal",
            customer_id=customer_id or "anonymous",
            temp_session_id=temp_session_id,
            temp_device_id=temp_device_id,
            created_at=utcnow(),
            updated_at=utcnow()
        )
        
        db.add(conversation)
        from app.services.statistics_service import StatisticsService
        await StatisticsService.record_conversation_created(db, conversation.created_at)
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"创建对话: {conversation_id}")
        return conversation
    
    @staticmethod
    async def get_conversation(
        db: AsyncSession,
        conversation_id: str,
        include_messages: bool = False
    ) -> Optional[Conversation]:
        """
        获取对话详情
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            include_messages: 是否包含消息
        
        Returns:
            对话对象或None
        """
        if include_messages:
            stmt = (
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
        else:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    
    @staticmethod
    async def get_conversations(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        include_deleted: bool = False,
    ) -> Tuple[List[Conversation], int]:
        """
        获取对话列表（分页）
        
        Args:
            db: 数据库会话
            page: 页码（从1开始）
            page_size: 每页数量
            status: 状态筛选（可选）
            customer_id: 客户ID筛选（可选）
            include_deleted: 是否包含用户软删除的会话（管理员/客服用）
        
        Returns:
            (对话列表, 总数)
        """
        # 构建查询
        stmt = select(Conversation)
        count_stmt = select(func.count(Conversation.id))
        
        if not include_deleted:
            stmt = stmt.where(Conversation.is_deleted_by_user.is_(False))
            count_stmt = count_stmt.where(Conversation.is_deleted_by_user.is_(False))
        
        if status:
            stmt = stmt.where(Conversation.status == status)
            count_stmt = count_stmt.where(Conversation.status == status)
        
        if customer_id:
            stmt = stmt.where(Conversation.customer_id == customer_id)
            count_stmt = count_stmt.where(Conversation.customer_id == customer_id)
        
        # 按更新时间降序排列
        stmt = stmt.order_by(Conversation.updated_at.desc())
        
        # 分页
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        # 执行查询
        result = await db.execute(stmt)
        conversations = list(result.scalars().all())
        
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return conversations, total
    
    @staticmethod
    async def update_conversation(
        db: AsyncSession,
        conversation_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[Conversation]:
        """
        更新对话
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            title: 新标题（可选）
            status: 新状态（可选）
        
        Returns:
            更新后的对话对象或None
        """
        conversation = await ChatService.get_conversation(db, conversation_id)
        if not conversation:
            return None
        
        if title is not None:
            conversation.title = title
        if status is not None:
            conversation.status = status
        
        conversation.updated_at = utcnow()
        
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"更新对话: {conversation_id}")
        return conversation
    
    @staticmethod
    async def delete_conversation(
        db: AsyncSession,
        conversation_id: str,
        deleted_by_customer_id: Optional[str] = None,
    ) -> bool:
        """
        软删除对话（用户视角隐藏，管理员仍可见）
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            deleted_by_customer_id: 执行删除的客户ID
        
        Returns:
            是否删除成功
        """
        conversation = await ChatService.get_conversation(db, conversation_id)
        if not conversation:
            return False
        
        conversation.is_deleted_by_user = True
        conversation.deleted_by_customer_id = deleted_by_customer_id
        conversation.deleted_at = utcnow()
        await db.commit()
        
        logger.info(f"软删除对话: {conversation_id} (by {deleted_by_customer_id})")
        return True

    @staticmethod
    async def hard_delete_conversation(
        db: AsyncSession,
        conversation_id: str,
    ) -> bool:
        """
        物理删除对话（级联删除消息），仅管理员使用。
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
        
        Returns:
            是否删除成功
        """
        conversation = await ChatService.get_conversation(db, conversation_id)
        if not conversation:
            return False
        
        await db.delete(conversation)
        await db.commit()
        
        logger.info(f"物理删除对话: {conversation_id}")
        return True
    
    @staticmethod
    async def delete_all_conversations(db: AsyncSession) -> int:
        """
        删除所有对话
        
        Args:
            db: 数据库会话
        
        Returns:
            删除的对话数量
        """
        # 先获取数量
        count_stmt = select(func.count(Conversation.id))
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 删除所有对话（消息会级联删除）
        stmt = delete(Conversation)
        await db.execute(stmt)
        await db.commit()
        
        logger.info(f"删除所有对话，共 {total} 条")
        return total

    
    # ==================== 消息管理 ====================
    
    @staticmethod
    async def add_message(
        db: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
        confidence: Optional[float] = None,
        rag_trace: Optional[Dict[str, Any]] = None
    ) -> Optional[Message]:
        """
        添加消息到对话
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            role: 角色（user/assistant/human）
            content: 消息内容
            confidence: 置信度（可选）
            rag_trace: RAG追踪信息（可选）
        
        Returns:
            新创建的消息对象或None
        """
        # 验证对话存在
        conversation = await ChatService.get_conversation(db, conversation_id)
        if not conversation:
            logger.warning(f"对话不存在: {conversation_id}")
            return None
        
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            confidence=confidence,
            rag_trace=rag_trace,
            timestamp=utcnow()
        )
        
        db.add(message)
        from app.services.statistics_service import StatisticsService
        await StatisticsService.record_message_created(db, role=role, created_at=message.timestamp)
        
        # 更新对话的更新时间
        conversation.updated_at = utcnow()
        
        # 如果是第一条用户消息，更新对话标题
        if role == "user" and conversation.title == "新对话":
            # 截取前30个字符作为标题
            conversation.title = content[:30] + ("..." if len(content) > 30 else "")
        
        await db.commit()
        await db.refresh(message)
        
        return message
    
    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: str,
        page: int = 1,
        page_size: int = 20,
        include_deleted: bool = False,
        since_id: Optional[int] = None,
    ) -> Tuple[List[Message], int]:
        """
        获取对话消息（分页）
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            page: 页码（从1开始）
            page_size: 每页数量
            include_deleted: 是否包含被用户软删除消息（管理员排查用）
            since_id: 增量拉取——仅返回 id > since_id 的消息（忽略分页）
        
        Returns:
            (消息列表, 总数)
        """
        # 构建查询
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.asc())
        )
        
        count_stmt = (
            select(func.count(Message.id))
            .where(Message.conversation_id == conversation_id)
        )
        if not include_deleted:
            stmt = stmt.where(Message.is_deleted_by_user.is_(False))
            count_stmt = count_stmt.where(Message.is_deleted_by_user.is_(False))

        if since_id is not None:
            # 增量模式：只返回 id > since_id 的消息，忽略分页
            stmt = stmt.where(Message.id > since_id)
            count_stmt = count_stmt.where(Message.id > since_id)
        else:
            # 分页模式
            offset = (page - 1) * page_size
            stmt = stmt.offset(offset).limit(page_size)
        
        # 执行查询
        result = await db.execute(stmt)
        messages = list(result.scalars().all())
        
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return messages, total
    
    @staticmethod
    async def get_all_messages(
        db: AsyncSession,
        conversation_id: str,
        include_deleted: bool = False,
    ) -> List[Message]:
        """
        获取对话的所有消息（用于上下文构建）
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            include_deleted: 是否包含被用户软删除消息
        
        Returns:
            消息列表（按时间升序）
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.asc())
        )
        if not include_deleted:
            stmt = stmt.where(Message.is_deleted_by_user.is_(False))
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_message_count(
        db: AsyncSession,
        conversation_id: str,
        include_deleted: bool = False,
    ) -> int:
        """
        获取对话消息数量
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            include_deleted: 是否包含被用户软删除消息
        
        Returns:
            消息数量
        """
        stmt = (
            select(func.count(Message.id))
            .where(Message.conversation_id == conversation_id)
        )
        if not include_deleted:
            stmt = stmt.where(Message.is_deleted_by_user.is_(False))
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def get_message_counts_for_conversations(
        db: AsyncSession,
        conversation_ids: List[str],
        include_deleted: bool = False,
    ) -> Dict[str, int]:
        """
        批量获取多个会话的消息数量，避免会话列表上的 N+1 查询。
        """
        if not conversation_ids:
            return {}

        stmt = (
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
        )
        if not include_deleted:
            stmt = stmt.where(Message.is_deleted_by_user.is_(False))
        stmt = stmt.group_by(Message.conversation_id)

        result = await db.execute(stmt)
        rows = result.all()
        return {conversation_id: int(count or 0) for conversation_id, count in rows}

    @staticmethod
    async def get_message(
        db: AsyncSession,
        message_id: int,
    ) -> Optional[Message]:
        """按ID获取消息"""
        stmt = select(Message).where(Message.id == message_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def soft_delete_message_by_user(
        db: AsyncSession,
        message: Message,
        deleted_by_customer_id: str,
    ) -> Message:
        """用户软删除消息（仅从用户视角隐藏，管理员可见）。"""
        message.is_deleted_by_user = True
        message.deleted_by_customer_id = deleted_by_customer_id
        message.deleted_at = utcnow()
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def hard_delete_message(
        db: AsyncSession,
        message: Message,
    ) -> None:
        """管理员最终删除消息（物理删除）。"""
        await db.delete(message)
        await db.commit()

    @staticmethod
    async def count_messages_by_date_range(
        db: AsyncSession,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> int:
        """统计指定日期范围内的消息数量（全局，管理员用）。"""
        stmt = select(func.count(Message.id))
        if before:
            stmt = stmt.where(Message.timestamp < before)
        if after:
            stmt = stmt.where(Message.timestamp >= after)
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def batch_delete_messages_by_date_range(
        db: AsyncSession,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> int:
        """物理删除指定日期范围内的消息（全局，管理员用）。"""
        stmt = delete(Message)
        if before:
            stmt = stmt.where(Message.timestamp < before)
        if after:
            stmt = stmt.where(Message.timestamp >= after)
        result = await db.execute(stmt)
        await db.commit()
        count = result.rowcount or 0
        logger.info(f"批量删除消息: {count} 条 (before={before}, after={after})")
        return count


    
    @staticmethod
    async def migrate_conversations(
        db: AsyncSession,
        from_customer_id: str,
        to_customer_id: str
    ) -> int:
        """
        Migrate conversations from one customer_id to another.
        Used when a guest visitor registers or logs in.

        Returns:
            Number of conversations migrated
        """
        stmt = (
            update(Conversation)
            .where(Conversation.customer_id == from_customer_id)
            .values(customer_id=to_customer_id)
        )
        result = await db.execute(stmt)
        await db.commit()
        count = result.rowcount
        if count > 0:
            logger.info(f"Migrated {count} conversations from {from_customer_id} to {to_customer_id}")
        return count

    @staticmethod
    async def migrate_guest_conversations(
        db: AsyncSession,
        to_customer_id: str,
        visitor_id: Optional[str] = None,
        device_id: Optional[str] = None,
        conversation_ids: Optional[List[str]] = None,
    ) -> int:
        """
        访客会话合并到用户账号，支持多种匹配条件：
        1) visitor_id（主路径）
        2) temp_device_id（同设备回收）
        3) conversation_ids（指定会话回收）
        """
        conditions = []

        if visitor_id and visitor_id.startswith("visitor_"):
            conditions.append(Conversation.customer_id == visitor_id)
            conditions.append(Conversation.temp_session_id == visitor_id)

        if device_id:
            conditions.append(Conversation.temp_device_id == device_id)

        if conversation_ids:
            safe_ids = [cid for cid in conversation_ids if isinstance(cid, str) and cid]
            if safe_ids:
                conditions.append(Conversation.id.in_(safe_ids))

        if not conditions:
            return 0

        stmt = (
            update(Conversation)
            .where(Conversation.customer_id.like("visitor_%"))
            .where(or_(*conditions))
            .values(customer_id=to_customer_id)
        )
        result = await db.execute(stmt)
        await db.commit()
        count = result.rowcount or 0
        if count > 0:
            logger.info(
                "Migrated %s guest conversations to %s (visitor_id=%s, device_id=%s, ids=%s)",
                count,
                to_customer_id,
                visitor_id,
                device_id,
                len(conversation_ids or []),
            )
        return count

    @staticmethod
    def messages_to_history(
        messages: List[Message],
        max_messages: int = 12,
        max_chars: int = 6000,
    ) -> List[Dict[str, str]]:
        """
        将消息列表转换为历史记录格式（用于LLM调用），
        按条数与字符数双限制裁剪，保留最近的消息。
        
        Args:
            messages: 消息列表（按时间升序）
            max_messages: 最大保留条数（默认 12）
            max_chars: 最大保留字符数（默认 6000）
        
        Returns:
            历史记录列表 [{"role": "user", "content": "..."}, ...]
        """
        # 先做角色过滤
        all_history = []
        for msg in messages:
            if msg.role in ("user", "assistant"):
                all_history.append({
                    "role": msg.role,
                    "content": msg.content
                })
            elif msg.role == "human":
                all_history.append({
                    "role": "assistant",
                    "content": msg.content
                })

        # 按条数限制：保留最近的 max_messages 条
        if max_messages > 0 and len(all_history) > max_messages:
            all_history = all_history[-max_messages:]

        # 按字符数限制：从最新往前累加，超出则截断
        if max_chars > 0:
            total_chars = 0
            cut_idx = len(all_history)
            for i in range(len(all_history) - 1, -1, -1):
                total_chars += len(all_history[i]["content"])
                if total_chars > max_chars:
                    cut_idx = i + 1
                    break
            if cut_idx > 0 and cut_idx < len(all_history):
                all_history = all_history[cut_idx:]

        return all_history

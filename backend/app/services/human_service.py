# -*- coding: utf-8 -*-
"""
人工客服服务模块 - Human Service

功能:
- 对话状态转换
- 待处理列表管理
- 人工客服接入/关闭
"""

import logging
from typing import List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


# 对话状态常量
class ConversationStatus:
    """对话状态枚举"""
    NORMAL = "normal"
    PENDING_HUMAN = "pending_human"
    HUMAN_HANDLING = "human_handling"
    HUMAN_CLOSED = "human_closed"


# 有效的状态转换映射
VALID_STATUS_TRANSITIONS = {
    ConversationStatus.NORMAL: [ConversationStatus.PENDING_HUMAN],
    ConversationStatus.PENDING_HUMAN: [ConversationStatus.HUMAN_HANDLING, ConversationStatus.NORMAL],
    ConversationStatus.HUMAN_HANDLING: [ConversationStatus.HUMAN_CLOSED],
    ConversationStatus.HUMAN_CLOSED: [ConversationStatus.NORMAL],
}


class HumanServiceError(Exception):
    """人工客服服务错误"""
    def __init__(self, message: str, code: str = "HUMAN_SERVICE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class HumanService:
    """人工客服服务类"""
    
    @staticmethod
    def is_valid_transition(from_status: str, to_status: str) -> bool:
        """
        检查状态转换是否有效
        
        Args:
            from_status: 当前状态
            to_status: 目标状态
        
        Returns:
            是否为有效转换
        """
        valid_targets = VALID_STATUS_TRANSITIONS.get(from_status, [])
        return to_status in valid_targets

    
    @staticmethod
    async def get_pending_conversations(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Conversation], int]:
        """
        获取待处理对话列表（状态为pending_human）
        
        Args:
            db: 数据库会话
            page: 页码（从1开始）
            page_size: 每页数量
        
        Returns:
            (对话列表, 总数)
        """
        # 构建查询
        stmt = (
            select(Conversation)
            .where(Conversation.status == ConversationStatus.PENDING_HUMAN)
            .order_by(Conversation.updated_at.asc())  # 按等待时间升序，先来先服务
        )
        
        count_stmt = (
            select(func.count(Conversation.id))
            .where(Conversation.status == ConversationStatus.PENDING_HUMAN)
        )
        
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
    async def get_handling_conversations(
        db: AsyncSession,
        agent_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Conversation], int]:
        """
        获取正在处理的对话列表
        
        Args:
            db: 数据库会话
            agent_id: 客服用户ID（None则返回所有，用于管理员）
            page: 页码
            page_size: 每页数量
        
        Returns:
            (对话列表, 总数)
        """
        conditions = [Conversation.status == ConversationStatus.HUMAN_HANDLING]
        if agent_id is not None:
            conditions.append(Conversation.human_agent_id == agent_id)

        stmt = (
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc())
        )
        
        count_stmt = (
            select(func.count(Conversation.id))
            .where(*conditions)
        )
        
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        result = await db.execute(stmt)
        conversations = list(result.scalars().all())
        
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return conversations, total

    
    @staticmethod
    async def transfer_to_human(
        db: AsyncSession,
        conversation_id: str,
        reason: Optional[str] = None
    ) -> Conversation:
        """
        将对话转接到人工客服
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            reason: 转人工原因
        
        Returns:
            更新后的对话对象
        
        Raises:
            HumanServiceError: 如果对话不存在或状态转换无效
        """
        # 获取对话
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
        
        # 检查状态转换是否有效
        if not HumanService.is_valid_transition(
            conversation.status, ConversationStatus.PENDING_HUMAN
        ):
            raise HumanServiceError(
                f"当前状态({conversation.status})不允许转人工",
                "INVALID_STATUS_TRANSITION"
            )
        
        # 更新状态
        conversation.status = ConversationStatus.PENDING_HUMAN
        conversation.updated_at = utcnow()
        
        # 添加系统消息
        reason_text = f"（原因：{reason}）" if reason else ""
        system_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=f"您的对话已转接人工客服{reason_text}，请稍候...",
            timestamp=utcnow()
        )
        db.add(system_message)
        
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"对话 {conversation_id} 已转接人工客服")
        return conversation
    
    @staticmethod
    async def accept_conversation(
        db: AsyncSession,
        conversation_id: str,
        agent_id: int
    ) -> Conversation:
        """
        客服接入对话（原子操作，防止并发竞态）

        使用条件 UPDATE 确保只有一个客服能成功接入：
        UPDATE ... WHERE id = ? AND status = 'pending_human'
        如果 rowcount == 0，说明已被其他客服抢先接入。
        """
        from sqlalchemy import update as sa_update

        # 原子更新：仅当 status 仍为 pending_human 时才更新
        stmt = (
            sa_update(Conversation)
            .where(Conversation.id == conversation_id)
            .where(Conversation.status == ConversationStatus.PENDING_HUMAN)
            .values(
                status=ConversationStatus.HUMAN_HANDLING,
                human_agent_id=agent_id,
                updated_at=utcnow(),
            )
        )
        result = await db.execute(stmt)

        if result.rowcount == 0:
            # 可能是对话不存在，也可能已被其他客服接入
            check = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = check.scalar_one_or_none()
            if not conv:
                raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
            raise HumanServiceError(
                "该对话已被其他客服接入或状态已变更",
                "ALREADY_ACCEPTED"
            )

        # 添加系统消息
        system_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="人工客服已接入，请问有什么可以帮您？",
            timestamp=utcnow()
        )
        db.add(system_message)

        await db.commit()

        # 重新查询获取最新对象
        refresh_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = refresh_result.scalar_one()

        logger.info(f"客服 {agent_id} 已接入对话 {conversation_id}（原子操作）")
        return conversation


    
    @staticmethod
    async def close_human_service(
        db: AsyncSession,
        conversation_id: str,
        agent_id: int
    ) -> Conversation:
        """
        关闭人工服务
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            agent_id: 客服用户ID
        
        Returns:
            更新后的对话对象
        
        Raises:
            HumanServiceError: 如果对话不存在、状态转换无效或非当前客服
        """
        # 获取对话
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
        
        # 检查是否是当前处理的客服
        if conversation.human_agent_id != agent_id:
            raise HumanServiceError(
                "只有当前处理的客服才能关闭服务",
                "NOT_CURRENT_AGENT"
            )
        
        # 检查状态转换是否有效
        if not HumanService.is_valid_transition(
            conversation.status, ConversationStatus.HUMAN_CLOSED
        ):
            raise HumanServiceError(
                f"当前状态({conversation.status})不允许关闭",
                "INVALID_STATUS_TRANSITION"
            )
        
        # 更新状态
        conversation.status = ConversationStatus.HUMAN_CLOSED
        conversation.updated_at = utcnow()
        
        # 添加系统消息
        system_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="人工客服服务已结束，感谢您的咨询。如需继续咨询，可以继续发送消息。",
            timestamp=utcnow()
        )
        db.add(system_message)
        
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"客服 {agent_id} 已关闭对话 {conversation_id} 的人工服务")
        return conversation
    
    @staticmethod
    async def return_to_ai(
        db: AsyncSession,
        conversation_id: str
    ) -> Conversation:
        """
        将对话返回AI模式
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
        
        Returns:
            更新后的对话对象
        
        Raises:
            HumanServiceError: 如果对话不存在或状态转换无效
        """
        # 获取对话
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
        
        # 检查状态转换是否有效
        if not HumanService.is_valid_transition(
            conversation.status, ConversationStatus.NORMAL
        ):
            raise HumanServiceError(
                f"当前状态({conversation.status})不允许返回AI模式",
                "INVALID_STATUS_TRANSITION"
            )
        
        # 更新状态
        conversation.status = ConversationStatus.NORMAL
        conversation.human_agent_id = None
        conversation.updated_at = utcnow()
        
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"对话 {conversation_id} 已返回AI模式")
        return conversation

    
    @staticmethod
    async def send_human_message(
        db: AsyncSession,
        conversation_id: str,
        agent_id: int,
        content: str
    ) -> Message:
        """
        客服发送消息
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            agent_id: 客服用户ID
            content: 消息内容
        
        Returns:
            新创建的消息对象
        
        Raises:
            HumanServiceError: 如果对话不存在、状态不正确或非当前客服
        """
        # 获取对话
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
        
        # 检查状态
        if conversation.status != ConversationStatus.HUMAN_HANDLING:
            raise HumanServiceError(
                f"当前状态({conversation.status})不允许发送人工消息",
                "INVALID_STATUS"
            )
        
        # 检查是否是当前处理的客服
        if conversation.human_agent_id != agent_id:
            raise HumanServiceError(
                "只有当前处理的客服才能发送消息",
                "NOT_CURRENT_AGENT"
            )
        
        # 创建消息
        # 获取客服显示名称
        agent_stmt = select(User).where(User.id == agent_id)
        agent_result = await db.execute(agent_stmt)
        agent = agent_result.scalar_one_or_none()
        agent_name = agent.display_name or agent.username if agent else None
        
        message = Message(
            conversation_id=conversation_id,
            role="human",
            content=content,
            human_agent_name=agent_name,
            timestamp=utcnow()
        )
        db.add(message)
        
        # 更新对话时间
        conversation.updated_at = utcnow()
        
        await db.commit()
        await db.refresh(message)
        
        logger.info(f"客服 {agent_id} 在对话 {conversation_id} 发送消息")
        return message
    
    @staticmethod
    async def get_conversation_with_messages(
        db: AsyncSession,
        conversation_id: str
    ) -> Optional[Conversation]:
        """
        获取对话及其所有消息
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
        
        Returns:
            对话对象（包含消息）或None
        """
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def cancel_transfer(
        db: AsyncSession,
        conversation_id: str
    ) -> Conversation:
        """
        取消转人工（从pending_human返回normal）
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
        
        Returns:
            更新后的对话对象
        
        Raises:
            HumanServiceError: 如果对话不存在或状态不是pending_human
        """
        # 获取对话
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HumanServiceError("对话不存在", "CONVERSATION_NOT_FOUND")
        
        # 检查状态
        if conversation.status != ConversationStatus.PENDING_HUMAN:
            raise HumanServiceError(
                f"当前状态({conversation.status})不允许取消转人工",
                "INVALID_STATUS"
            )
        
        # 更新状态
        conversation.status = ConversationStatus.NORMAL
        conversation.updated_at = utcnow()
        
        # 添加系统消息
        system_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="转人工请求已取消，继续为您提供AI服务。",
            timestamp=utcnow()
        )
        db.add(system_message)
        
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"对话 {conversation_id} 取消转人工")
        return conversation

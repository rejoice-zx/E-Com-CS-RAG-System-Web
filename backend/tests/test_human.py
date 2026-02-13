# -*- coding: utf-8 -*-
"""Human Service Tests"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.human_service import (
    HumanService,
    HumanServiceError,
    ConversationStatus,
    VALID_STATUS_TRANSITIONS
)
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService


class TestStatusTransitions:
    """状态转换测试"""
    
    def test_valid_transition_normal_to_pending(self):
        """测试normal到pending_human的有效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.NORMAL,
            ConversationStatus.PENDING_HUMAN
        ) is True
    
    def test_valid_transition_pending_to_handling(self):
        """测试pending_human到human_handling的有效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.PENDING_HUMAN,
            ConversationStatus.HUMAN_HANDLING
        ) is True
    
    def test_valid_transition_pending_to_normal(self):
        """测试pending_human到normal的有效转换（取消转人工）"""
        assert HumanService.is_valid_transition(
            ConversationStatus.PENDING_HUMAN,
            ConversationStatus.NORMAL
        ) is True
    
    def test_valid_transition_handling_to_closed(self):
        """测试human_handling到human_closed的有效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.HUMAN_HANDLING,
            ConversationStatus.HUMAN_CLOSED
        ) is True
    
    def test_valid_transition_closed_to_normal(self):
        """测试human_closed到normal的有效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.HUMAN_CLOSED,
            ConversationStatus.NORMAL
        ) is True
    
    def test_invalid_transition_normal_to_handling(self):
        """测试normal直接到human_handling的无效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.NORMAL,
            ConversationStatus.HUMAN_HANDLING
        ) is False
    
    def test_invalid_transition_normal_to_closed(self):
        """测试normal直接到human_closed的无效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.NORMAL,
            ConversationStatus.HUMAN_CLOSED
        ) is False
    
    def test_invalid_transition_handling_to_pending(self):
        """测试human_handling到pending_human的无效转换"""
        assert HumanService.is_valid_transition(
            ConversationStatus.HUMAN_HANDLING,
            ConversationStatus.PENDING_HUMAN
        ) is False


class TestTransferToHuman:
    """转人工测试"""
    
    @pytest.mark.asyncio
    async def test_transfer_to_human_success(self, test_session: AsyncSession):
        """测试成功转人工"""
        # 创建对话
        conversation = await ChatService.create_conversation(test_session, title="测试对话")
        assert conversation.status == ConversationStatus.NORMAL
        
        # 转人工
        updated = await HumanService.transfer_to_human(
            test_session, conversation.id, reason="需要人工帮助"
        )
        
        assert updated.status == ConversationStatus.PENDING_HUMAN
    
    @pytest.mark.asyncio
    async def test_transfer_to_human_not_found(self, test_session: AsyncSession):
        """测试转人工对话不存在"""
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.transfer_to_human(test_session, "non-existent-id")
        
        assert exc_info.value.code == "CONVERSATION_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_transfer_to_human_invalid_status(self, test_session: AsyncSession):
        """测试从非normal状态转人工"""
        conversation = await ChatService.create_conversation(test_session)
        
        # 先转人工
        await HumanService.transfer_to_human(test_session, conversation.id)
        
        # 再次转人工应该失败
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.transfer_to_human(test_session, conversation.id)
        
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"



class TestAcceptConversation:
    """接入对话测试"""
    
    @pytest.mark.asyncio
    async def test_accept_conversation_success(self, test_session: AsyncSession, test_user):
        """测试成功接入对话"""
        # 创建对话并转人工
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        
        # 接入对话
        updated = await HumanService.accept_conversation(
            test_session, conversation.id, test_user.id
        )
        
        assert updated.status == ConversationStatus.HUMAN_HANDLING
        assert updated.human_agent_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_accept_conversation_not_found(self, test_session: AsyncSession, test_user):
        """测试接入不存在的对话"""
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.accept_conversation(
                test_session, "non-existent-id", test_user.id
            )
        
        assert exc_info.value.code == "CONVERSATION_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_accept_conversation_invalid_status(self, test_session: AsyncSession, test_user):
        """测试从非pending_human状态接入"""
        conversation = await ChatService.create_conversation(test_session)
        
        # 直接接入应该失败（原子更新：status != pending_human → ALREADY_ACCEPTED）
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.accept_conversation(
                test_session, conversation.id, test_user.id
            )
        
        assert exc_info.value.code == "ALREADY_ACCEPTED"


class TestCloseHumanService:
    """关闭人工服务测试"""
    
    @pytest.mark.asyncio
    async def test_close_human_service_success(self, test_session: AsyncSession, test_user):
        """测试成功关闭人工服务"""
        # 创建对话、转人工、接入
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        await HumanService.accept_conversation(test_session, conversation.id, test_user.id)
        
        # 关闭服务
        updated = await HumanService.close_human_service(
            test_session, conversation.id, test_user.id
        )
        
        assert updated.status == ConversationStatus.HUMAN_CLOSED
    
    @pytest.mark.asyncio
    async def test_close_human_service_not_current_agent(self, test_session: AsyncSession, test_user):
        """测试非当前客服关闭服务"""
        # 创建对话、转人工、接入
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        await HumanService.accept_conversation(test_session, conversation.id, test_user.id)
        
        # 用另一个用户ID关闭应该失败
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.close_human_service(
                test_session, conversation.id, test_user.id + 999
            )
        
        assert exc_info.value.code == "NOT_CURRENT_AGENT"
    
    @pytest.mark.asyncio
    async def test_close_human_service_invalid_status(self, test_session: AsyncSession, test_user):
        """测试从非human_handling状态关闭"""
        # 创建对话并转人工（但不接入）
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        
        # 尝试关闭应该失败（状态是pending_human，不是human_handling）
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.close_human_service(
                test_session, conversation.id, test_user.id
            )
        
        # 由于human_agent_id为None，会先检查到NOT_CURRENT_AGENT
        # 这是预期行为，因为只有当前处理的客服才能关闭
        assert exc_info.value.code == "NOT_CURRENT_AGENT"



class TestSendHumanMessage:
    """客服发送消息测试"""
    
    @pytest.mark.asyncio
    async def test_send_human_message_success(self, test_session: AsyncSession, test_user):
        """测试成功发送人工消息"""
        # 创建对话、转人工、接入
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        await HumanService.accept_conversation(test_session, conversation.id, test_user.id)
        
        # 发送消息
        message = await HumanService.send_human_message(
            test_session, conversation.id, test_user.id, "您好，有什么可以帮您？"
        )
        
        assert message.role == "human"
        assert message.content == "您好，有什么可以帮您？"
        assert message.conversation_id == conversation.id
    
    @pytest.mark.asyncio
    async def test_send_human_message_not_current_agent(self, test_session: AsyncSession, test_user):
        """测试非当前客服发送消息"""
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        await HumanService.accept_conversation(test_session, conversation.id, test_user.id)
        
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.send_human_message(
                test_session, conversation.id, test_user.id + 999, "消息"
            )
        
        assert exc_info.value.code == "NOT_CURRENT_AGENT"
    
    @pytest.mark.asyncio
    async def test_send_human_message_invalid_status(self, test_session: AsyncSession, test_user):
        """测试在非human_handling状态发送消息"""
        conversation = await ChatService.create_conversation(test_session)
        
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.send_human_message(
                test_session, conversation.id, test_user.id, "消息"
            )
        
        assert exc_info.value.code == "INVALID_STATUS"


class TestPendingConversations:
    """待处理对话列表测试"""
    
    @pytest.mark.asyncio
    async def test_get_pending_conversations(self, test_session: AsyncSession):
        """测试获取待处理对话列表"""
        # 创建多个对话并转人工
        for i in range(3):
            conv = await ChatService.create_conversation(test_session, title=f"对话{i}")
            await HumanService.transfer_to_human(test_session, conv.id)
        
        # 获取待处理列表
        conversations, total = await HumanService.get_pending_conversations(test_session)
        
        assert total == 3
        assert len(conversations) == 3
        # 验证都是pending_human状态
        for conv in conversations:
            assert conv.status == ConversationStatus.PENDING_HUMAN
    
    @pytest.mark.asyncio
    async def test_get_pending_conversations_pagination(self, test_session: AsyncSession):
        """测试待处理对话分页"""
        # 创建5个待处理对话
        for i in range(5):
            conv = await ChatService.create_conversation(test_session, title=f"对话{i}")
            await HumanService.transfer_to_human(test_session, conv.id)
        
        # 获取第一页
        conversations, total = await HumanService.get_pending_conversations(
            test_session, page=1, page_size=2
        )
        
        assert total == 5
        assert len(conversations) == 2
        
        # 获取第二页
        conversations2, _ = await HumanService.get_pending_conversations(
            test_session, page=2, page_size=2
        )
        
        assert len(conversations2) == 2
    
    @pytest.mark.asyncio
    async def test_pending_list_excludes_other_statuses(self, test_session: AsyncSession, test_user):
        """测试待处理列表不包含其他状态的对话"""
        # 创建normal状态对话
        conv1 = await ChatService.create_conversation(test_session, title="normal对话")
        
        # 创建pending_human状态对话
        conv2 = await ChatService.create_conversation(test_session, title="pending对话")
        await HumanService.transfer_to_human(test_session, conv2.id)
        
        # 创建human_handling状态对话
        conv3 = await ChatService.create_conversation(test_session, title="handling对话")
        await HumanService.transfer_to_human(test_session, conv3.id)
        await HumanService.accept_conversation(test_session, conv3.id, test_user.id)
        
        # 获取待处理列表
        conversations, total = await HumanService.get_pending_conversations(test_session)
        
        assert total == 1
        assert conversations[0].id == conv2.id


class TestReturnToAI:
    """返回AI模式测试"""
    
    @pytest.mark.asyncio
    async def test_return_to_ai_from_closed(self, test_session: AsyncSession, test_user):
        """测试从human_closed返回AI模式"""
        # 完整流程：创建 -> 转人工 -> 接入 -> 关闭
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        await HumanService.accept_conversation(test_session, conversation.id, test_user.id)
        await HumanService.close_human_service(test_session, conversation.id, test_user.id)
        
        # 返回AI模式
        updated = await HumanService.return_to_ai(test_session, conversation.id)
        
        assert updated.status == ConversationStatus.NORMAL
        assert updated.human_agent_id is None
    
    @pytest.mark.asyncio
    async def test_return_to_ai_invalid_status(self, test_session: AsyncSession):
        """测试从非human_closed状态返回AI"""
        conversation = await ChatService.create_conversation(test_session)
        
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.return_to_ai(test_session, conversation.id)
        
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


class TestCancelTransfer:
    """取消转人工测试"""
    
    @pytest.mark.asyncio
    async def test_cancel_transfer_success(self, test_session: AsyncSession):
        """测试成功取消转人工"""
        conversation = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conversation.id)
        
        # 取消转人工
        updated = await HumanService.cancel_transfer(test_session, conversation.id)
        
        assert updated.status == ConversationStatus.NORMAL
    
    @pytest.mark.asyncio
    async def test_cancel_transfer_invalid_status(self, test_session: AsyncSession):
        """测试从非pending_human状态取消"""
        conversation = await ChatService.create_conversation(test_session)
        
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.cancel_transfer(test_session, conversation.id)
        
        assert exc_info.value.code == "INVALID_STATUS"

# -*- coding: utf-8 -*-
"""Chat Service Tests"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_service import ChatService
from app.models.conversation import Conversation, Message


class TestConversationCRUD:
    """对话CRUD操作测试"""
    
    @pytest.mark.asyncio
    async def test_create_conversation(self, test_session: AsyncSession):
        """测试创建对话"""
        conversation = await ChatService.create_conversation(test_session, title="测试对话")
        
        assert conversation is not None
        assert conversation.id is not None
        assert len(conversation.id) == 36  # UUID格式
        assert conversation.title == "测试对话"
        assert conversation.status == "normal"
    
    @pytest.mark.asyncio
    async def test_create_conversation_default_title(self, test_session: AsyncSession):
        """测试创建对话默认标题"""
        conversation = await ChatService.create_conversation(test_session)
        
        assert conversation.title == "新对话"
    
    @pytest.mark.asyncio
    async def test_get_conversation(self, test_session: AsyncSession):
        """测试获取对话"""
        created = await ChatService.create_conversation(test_session, title="测试")
        
        retrieved = await ChatService.get_conversation(test_session, created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == "测试"
    
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, test_session: AsyncSession):
        """测试获取不存在的对话"""
        result = await ChatService.get_conversation(test_session, "non-existent-id")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_conversations_pagination(self, test_session: AsyncSession):
        """测试对话列表分页"""
        # 创建5个对话
        for i in range(5):
            await ChatService.create_conversation(test_session, title=f"对话{i}")
        
        # 获取第一页
        conversations, total = await ChatService.get_conversations(
            test_session, page=1, page_size=2
        )
        
        assert len(conversations) == 2
        assert total == 5
        
        # 获取第二页
        conversations2, _ = await ChatService.get_conversations(
            test_session, page=2, page_size=2
        )
        
        assert len(conversations2) == 2
    
    @pytest.mark.asyncio
    async def test_update_conversation(self, test_session: AsyncSession):
        """测试更新对话"""
        conversation = await ChatService.create_conversation(test_session, title="原标题")
        
        updated = await ChatService.update_conversation(
            test_session, conversation.id, title="新标题", status="pending_human"
        )
        
        assert updated is not None
        assert updated.title == "新标题"
        assert updated.status == "pending_human"
    
    @pytest.mark.asyncio
    async def test_delete_conversation(self, test_session: AsyncSession):
        """测试软删除对话"""
        conversation = await ChatService.create_conversation(test_session)
        
        success = await ChatService.delete_conversation(test_session, conversation.id)
        
        assert success is True
        
        # 软删除后仍可通过 get_conversation 获取（管理员需要）
        result = await ChatService.get_conversation(test_session, conversation.id)
        assert result is not None
        assert result.is_deleted_by_user is True

        # 但在列表中默认不可见
        convs, total = await ChatService.get_conversations(test_session)
        conv_ids = {c.id for c in convs}
        assert conversation.id not in conv_ids

        # include_deleted=True 时可见
        convs2, total2 = await ChatService.get_conversations(test_session, include_deleted=True)
        conv_ids2 = {c.id for c in convs2}
        assert conversation.id in conv_ids2
    
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, test_session: AsyncSession):
        """测试删除不存在的对话"""
        success = await ChatService.delete_conversation(test_session, "non-existent")
        
        assert success is False



class TestMessageManagement:
    """消息管理测试"""
    
    @pytest.mark.asyncio
    async def test_add_message(self, test_session: AsyncSession):
        """测试添加消息"""
        conversation = await ChatService.create_conversation(test_session)
        
        message = await ChatService.add_message(
            test_session,
            conversation.id,
            role="user",
            content="你好"
        )
        
        assert message is not None
        assert message.role == "user"
        assert message.content == "你好"
        assert message.conversation_id == conversation.id
    
    @pytest.mark.asyncio
    async def test_add_message_updates_title(self, test_session: AsyncSession):
        """测试第一条用户消息更新对话标题"""
        conversation = await ChatService.create_conversation(test_session)
        assert conversation.title == "新对话"
        
        await ChatService.add_message(
            test_session,
            conversation.id,
            role="user",
            content="这是一个很长的问题内容用于测试标题截取功能"
        )
        
        # 重新获取对话
        updated = await ChatService.get_conversation(test_session, conversation.id)
        assert updated.title != "新对话"
        assert len(updated.title) <= 33  # 30字符 + "..."
    
    @pytest.mark.asyncio
    async def test_add_message_with_rag_trace(self, test_session: AsyncSession):
        """测试添加带RAG追踪的消息"""
        conversation = await ChatService.create_conversation(test_session)
        
        rag_trace = {
            "query": "测试查询",
            "confidence": 0.85,
            "retrieved_items": [{"id": "1", "score": 0.9}]
        }
        
        message = await ChatService.add_message(
            test_session,
            conversation.id,
            role="assistant",
            content="回复内容",
            confidence=0.85,
            rag_trace=rag_trace
        )
        
        assert message.confidence == 0.85
        assert message.rag_trace == rag_trace
    
    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, test_session: AsyncSession):
        """测试消息分页"""
        conversation = await ChatService.create_conversation(test_session)
        
        # 添加5条消息
        for i in range(5):
            await ChatService.add_message(
                test_session,
                conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"消息{i}"
            )
        
        # 获取第一页
        messages, total = await ChatService.get_messages(
            test_session, conversation.id, page=1, page_size=2
        )
        
        assert len(messages) == 2
        assert total == 5
        # 验证按时间升序
        assert messages[0].content == "消息0"
        assert messages[1].content == "消息1"
    
    @pytest.mark.asyncio
    async def test_get_all_messages(self, test_session: AsyncSession):
        """测试获取所有消息"""
        conversation = await ChatService.create_conversation(test_session)
        
        for i in range(3):
            await ChatService.add_message(
                test_session,
                conversation.id,
                role="user",
                content=f"消息{i}"
            )
        
        messages = await ChatService.get_all_messages(test_session, conversation.id)
        
        assert len(messages) == 3
    
    @pytest.mark.asyncio
    async def test_get_message_count(self, test_session: AsyncSession):
        """测试获取消息数量"""
        conversation = await ChatService.create_conversation(test_session)
        
        for i in range(3):
            await ChatService.add_message(
                test_session,
                conversation.id,
                role="user",
                content=f"消息{i}"
            )
        
        count = await ChatService.get_message_count(test_session, conversation.id)
        
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_messages_to_history(self, test_session: AsyncSession):
        """测试消息转换为历史格式"""
        conversation = await ChatService.create_conversation(test_session)
        
        await ChatService.add_message(test_session, conversation.id, "user", "问题1")
        await ChatService.add_message(test_session, conversation.id, "assistant", "回答1")
        await ChatService.add_message(test_session, conversation.id, "user", "问题2")
        
        messages = await ChatService.get_all_messages(test_session, conversation.id)
        history = ChatService.messages_to_history(messages)
        
        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "问题1"}
        assert history[1] == {"role": "assistant", "content": "回答1"}
        assert history[2] == {"role": "user", "content": "问题2"}


class TestConversationIDUniqueness:
    """对话ID唯一性测试"""
    
    @pytest.mark.asyncio
    async def test_conversation_ids_unique(self, test_session: AsyncSession):
        """测试多个对话ID唯一"""
        ids = set()
        
        for _ in range(10):
            conversation = await ChatService.create_conversation(test_session)
            assert conversation.id not in ids
            ids.add(conversation.id)
        
        assert len(ids) == 10


class TestCascadeDelete:
    """级联删除测试"""
    
    @pytest.mark.asyncio
    async def test_delete_conversation_cascades_messages(self, test_session: AsyncSession):
        """测试删除对话级联删除消息"""
        conversation = await ChatService.create_conversation(test_session)
        
        # 添加消息
        for i in range(3):
            await ChatService.add_message(
                test_session,
                conversation.id,
                role="user",
                content=f"消息{i}"
            )
        
        # 验证消息存在
        count = await ChatService.get_message_count(test_session, conversation.id)
        assert count == 3
        
        # 删除对话（软删除）
        await ChatService.delete_conversation(test_session, conversation.id)
        
        # 软删除后对话仍存在，消息也仍存在
        result = await ChatService.get_conversation(test_session, conversation.id)
        assert result is not None
        assert result.is_deleted_by_user is True

        # 物理删除后对话和消息都被删除
        await ChatService.hard_delete_conversation(test_session, conversation.id)
        result2 = await ChatService.get_conversation(test_session, conversation.id)
        assert result2 is None

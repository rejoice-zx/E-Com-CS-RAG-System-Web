# -*- coding: utf-8 -*-
"""
高并发场景集成测试

覆盖：
- 多客服同时接入同一会话的竞态
- 高频消息发送下的增量同步一致性
- since_id 增量拉取的正确性
"""

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_service import ChatService
from app.services.human_service import HumanService, HumanServiceError
from app.services.auth_service import AuthService


class TestConcurrentAccept:
    """多客服并发接入同一会话的竞态测试"""

    @pytest_asyncio.fixture
    async def agents(self, test_session: AsyncSession):
        """创建多个客服用户"""
        agents = []
        for i in range(5):
            agent = await AuthService.create_user(
                test_session,
                username=f"agent_{i}",
                password="password",
                role="cs",
                display_name=f"Agent {i}",
            )
            agents.append(agent)
        return agents

    @pytest.mark.asyncio
    async def test_only_one_agent_accepts(self, test_session: AsyncSession, agents):
        """5 个客服同时接入同一会话，只有 1 个成功"""
        conv = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conv.id)

        results = []
        for agent in agents:
            try:
                c = await HumanService.accept_conversation(
                    test_session, conv.id, agent.id
                )
                results.append(("ok", agent.id))
            except HumanServiceError as e:
                results.append((e.code, agent.id))

        ok_count = sum(1 for r in results if r[0] == "ok")
        already_count = sum(1 for r in results if r[0] == "ALREADY_ACCEPTED")

        assert ok_count == 1, f"Expected exactly 1 success, got {ok_count}: {results}"
        assert already_count == 4, f"Expected 4 ALREADY_ACCEPTED, got {already_count}"

    @pytest.mark.asyncio
    async def test_accept_nonexistent_conversation(self, test_session: AsyncSession, agents):
        """接入不存在的会话应返回 CONVERSATION_NOT_FOUND"""
        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.accept_conversation(
                test_session, "nonexistent-id", agents[0].id
            )
        assert exc_info.value.code == "CONVERSATION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_double_accept_same_agent(self, test_session: AsyncSession, agents):
        """同一客服重复接入应失败"""
        conv = await ChatService.create_conversation(test_session)
        await HumanService.transfer_to_human(test_session, conv.id)

        await HumanService.accept_conversation(test_session, conv.id, agents[0].id)

        with pytest.raises(HumanServiceError) as exc_info:
            await HumanService.accept_conversation(test_session, conv.id, agents[0].id)
        assert exc_info.value.code == "ALREADY_ACCEPTED"


class TestHighFrequencyMessages:
    """高频消息发送与增量同步测试"""

    @pytest.mark.asyncio
    async def test_rapid_message_creation(self, test_session: AsyncSession):
        """快速连续创建 50 条消息，验证全部落库且 ID 递增"""
        conv = await ChatService.create_conversation(test_session)

        msg_ids = []
        for i in range(50):
            role = "user" if i % 2 == 0 else "assistant"
            msg = await ChatService.add_message(
                test_session, conv.id, role=role, content=f"Message {i}"
            )
            assert msg is not None
            msg_ids.append(msg.id)

        # 验证 ID 严格递增
        for i in range(1, len(msg_ids)):
            assert msg_ids[i] > msg_ids[i - 1], f"IDs not strictly increasing at index {i}"

        # 验证总数
        all_msgs, total = await ChatService.get_messages(
            test_session, conv.id, page=1, page_size=100
        )
        assert total == 50
        assert len(all_msgs) == 50

    @pytest.mark.asyncio
    async def test_since_id_incremental_fetch(self, test_session: AsyncSession):
        """验证 since_id 增量拉取只返回新消息"""
        conv = await ChatService.create_conversation(test_session)

        # 创建前 10 条消息
        first_batch_ids = []
        for i in range(10):
            msg = await ChatService.add_message(
                test_session, conv.id, role="user", content=f"Batch1 msg {i}"
            )
            first_batch_ids.append(msg.id)

        last_seen_id = first_batch_ids[-1]

        # 创建后 5 条消息
        second_batch_ids = []
        for i in range(5):
            msg = await ChatService.add_message(
                test_session, conv.id, role="assistant", content=f"Batch2 msg {i}"
            )
            second_batch_ids.append(msg.id)

        # 使用 since_id 拉取
        new_msgs, count = await ChatService.get_messages(
            test_session, conv.id, since_id=last_seen_id
        )

        assert count == 5, f"Expected 5 new messages, got {count}"
        assert len(new_msgs) == 5
        for msg in new_msgs:
            assert msg.id > last_seen_id
            assert msg.id in second_batch_ids

    @pytest.mark.asyncio
    async def test_since_id_no_new_messages(self, test_session: AsyncSession):
        """since_id 指向最新消息时应返回空"""
        conv = await ChatService.create_conversation(test_session)

        msg = await ChatService.add_message(
            test_session, conv.id, role="user", content="Only message"
        )

        new_msgs, count = await ChatService.get_messages(
            test_session, conv.id, since_id=msg.id
        )
        assert count == 0
        assert len(new_msgs) == 0

    @pytest.mark.asyncio
    async def test_since_id_with_soft_deleted(self, test_session: AsyncSession):
        """since_id 增量拉取应默认排除软删除消息"""
        conv = await ChatService.create_conversation(test_session)

        msg1 = await ChatService.add_message(
            test_session, conv.id, role="user", content="msg1"
        )
        msg2 = await ChatService.add_message(
            test_session, conv.id, role="assistant", content="msg2"
        )
        msg3 = await ChatService.add_message(
            test_session, conv.id, role="user", content="msg3"
        )

        # 软删除 msg3
        await ChatService.soft_delete_message_by_user(
            test_session, msg3, deleted_by_customer_id="test_user"
        )

        # since_id=msg1.id，应只返回 msg2（msg3 已软删除）
        new_msgs, count = await ChatService.get_messages(
            test_session, conv.id, since_id=msg1.id
        )
        assert count == 1
        assert new_msgs[0].id == msg2.id

        # include_deleted=True 时应返回 msg2 和 msg3
        new_msgs_all, count_all = await ChatService.get_messages(
            test_session, conv.id, since_id=msg1.id, include_deleted=True
        )
        assert count_all == 2


class TestMultiConversationIsolation:
    """多会话消息隔离测试"""

    @pytest.mark.asyncio
    async def test_since_id_cross_conversation_isolation(self, test_session: AsyncSession):
        """since_id 不应跨会话泄漏消息"""
        conv_a = await ChatService.create_conversation(test_session, title="Conv A")
        conv_b = await ChatService.create_conversation(test_session, title="Conv B")

        msg_a = await ChatService.add_message(
            test_session, conv_a.id, role="user", content="A msg"
        )
        msg_b = await ChatService.add_message(
            test_session, conv_b.id, role="user", content="B msg"
        )

        # 用 conv_a 的 since_id 查 conv_b，不应返回 conv_a 的消息
        new_msgs, count = await ChatService.get_messages(
            test_session, conv_b.id, since_id=0
        )
        assert count == 1
        assert new_msgs[0].content == "B msg"

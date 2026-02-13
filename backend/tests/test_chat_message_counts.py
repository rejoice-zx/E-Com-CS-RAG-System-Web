# -*- coding: utf-8 -*-
"""Tests for batched message counting."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_get_message_counts_for_conversations(test_session: AsyncSession):
    conversation_a = await ChatService.create_conversation(test_session)
    conversation_b = await ChatService.create_conversation(test_session)

    msg_a1 = await ChatService.add_message(test_session, conversation_a.id, role="user", content="a1")
    await ChatService.add_message(test_session, conversation_a.id, role="assistant", content="a2")
    await ChatService.add_message(test_session, conversation_b.id, role="user", content="b1")

    await ChatService.soft_delete_message_by_user(
        test_session,
        msg_a1,
        deleted_by_customer_id="user_1",
    )

    visible_counts = await ChatService.get_message_counts_for_conversations(
        test_session,
        [conversation_a.id, conversation_b.id],
        include_deleted=False,
    )
    all_counts = await ChatService.get_message_counts_for_conversations(
        test_session,
        [conversation_a.id, conversation_b.id],
        include_deleted=True,
    )

    assert visible_counts[conversation_a.id] == 1
    assert visible_counts[conversation_b.id] == 1
    assert all_counts[conversation_a.id] == 2
    assert all_counts[conversation_b.id] == 1

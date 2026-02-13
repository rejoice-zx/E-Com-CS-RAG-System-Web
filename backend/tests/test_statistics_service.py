# -*- coding: utf-8 -*-
"""Statistics service tests."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_service import ChatService
from app.services.statistics_service import StatisticsService
from app.utils.time import utcnow


@pytest.mark.asyncio
async def test_total_conversations_is_cumulative_after_conversation_delete(test_session: AsyncSession):
    conv = await ChatService.create_conversation(test_session, title="stats-conv", customer_id="user_1")
    await ChatService.add_message(test_session, conv.id, role="user", content="hello")

    before_delete = await StatisticsService.get_overview_stats(test_session)
    assert before_delete.total_conversations >= 1
    assert before_delete.total_messages >= 1

    ok = await ChatService.delete_conversation(test_session, conv.id)
    assert ok is True

    after_delete = await StatisticsService.get_overview_stats(test_session)
    assert after_delete.total_conversations == before_delete.total_conversations
    assert after_delete.total_messages == before_delete.total_messages


@pytest.mark.asyncio
async def test_get_daily_stats_supports_date_range(test_session: AsyncSession):
    base = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    day_minus_2 = base - timedelta(days=2)
    day_minus_1 = base - timedelta(days=1)
    today = base

    await StatisticsService.record_conversation_created(test_session, day_minus_1)
    await StatisticsService.record_message_created(test_session, role="user", created_at=day_minus_1)
    await StatisticsService.record_conversation_created(test_session, today)
    await StatisticsService.record_message_created(test_session, role="assistant", created_at=today)
    await test_session.commit()

    stats = await StatisticsService.get_daily_stats(
        test_session,
        start_date=day_minus_2.date(),
        end_date=today.date(),
    )
    assert len(stats) == 3
    assert stats[0].date == day_minus_2.strftime("%Y-%m-%d")
    assert stats[1].date == day_minus_1.strftime("%Y-%m-%d")
    assert stats[2].date == today.strftime("%Y-%m-%d")

    assert stats[0].conversations == 0
    assert stats[0].messages == 0
    assert stats[1].conversations == 1
    assert stats[1].messages == 1
    assert stats[2].conversations == 1
    assert stats[2].messages == 1


@pytest.mark.asyncio
async def test_clear_statistics_data_all_and_range(test_session: AsyncSession):
    base = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    day_minus_1 = base - timedelta(days=1)

    await StatisticsService.record_conversation_created(test_session, day_minus_1)
    await StatisticsService.record_message_created(test_session, role="user", created_at=day_minus_1)
    await StatisticsService.record_conversation_created(test_session, base)
    await StatisticsService.record_message_created(test_session, role="assistant", created_at=base)
    await test_session.commit()

    range_result = await StatisticsService.clear_statistics_data_by_range(
        test_session,
        start_date=day_minus_1.date(),
        end_date=day_minus_1.date(),
    )
    assert range_result["deleted_days"] == 1
    assert range_result["deleted_conversations"] == 1
    assert range_result["deleted_messages"] == 1

    mid_overview = await StatisticsService.get_overview_stats(test_session)
    assert mid_overview.total_conversations == 1
    assert mid_overview.total_messages == 1

    all_result = await StatisticsService.clear_all_statistics_data(test_session)
    assert all_result["deleted_days"] >= 1

    after_overview = await StatisticsService.get_overview_stats(test_session)
    assert after_overview.total_conversations == 0
    assert after_overview.total_messages == 0

# -*- coding: utf-8 -*-
"""Statistics service."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem
from app.models.product import Product
from app.models.statistics import StatisticsDaily
from app.models.user import User
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


@dataclass
class OverviewStats:
    total_conversations: int = 0
    total_messages: int = 0
    total_knowledge_items: int = 0
    total_products: int = 0
    total_users: int = 0
    conversations_today: int = 0
    conversations_this_week: int = 0
    conversations_this_month: int = 0
    avg_response_time_ms: float = 0.0
    success_rate: float = 0.0


@dataclass
class DailyStats:
    date: str
    conversations: int = 0
    messages: int = 0
    user_messages: int = 0
    assistant_messages: int = 0


@dataclass
class CategoryDistribution:
    knowledge_categories: Dict[str, int] = field(default_factory=dict)
    product_categories: Dict[str, int] = field(default_factory=dict)


class StatisticsService:
    """Statistics service for dashboard and reporting."""

    _question_counter: Counter = Counter()

    @classmethod
    async def _get_or_create_daily_bucket(cls, db: AsyncSession, target_date: date) -> StatisticsDaily:
        row = (
            await db.execute(select(StatisticsDaily).where(StatisticsDaily.date == target_date))
        ).scalar_one_or_none()
        if row:
            return row
        row = StatisticsDaily(date=target_date)
        db.add(row)
        await db.flush()
        return row

    @classmethod
    async def record_conversation_created(cls, db: AsyncSession, created_at=None) -> None:
        """Increment cumulative conversation counter by creation date."""
        event_time = created_at or utcnow()
        day_bucket = await cls._get_or_create_daily_bucket(db, event_time.date())
        day_bucket.conversations = int(day_bucket.conversations or 0) + 1
        day_bucket.updated_at = utcnow()

    @classmethod
    async def record_message_created(cls, db: AsyncSession, role: str, created_at=None) -> None:
        """Increment cumulative message counter by message timestamp."""
        event_time = created_at or utcnow()
        day_bucket = await cls._get_or_create_daily_bucket(db, event_time.date())
        day_bucket.messages = int(day_bucket.messages or 0) + 1
        if role == "user":
            day_bucket.user_messages = int(day_bucket.user_messages or 0) + 1
        elif role == "assistant":
            day_bucket.assistant_messages = int(day_bucket.assistant_messages or 0) + 1
        day_bucket.updated_at = utcnow()

    @classmethod
    async def get_overview_stats(cls, db: AsyncSession) -> OverviewStats:
        stats = OverviewStats()

        try:
            totals = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(StatisticsDaily.conversations), 0),
                        func.coalesce(func.sum(StatisticsDaily.messages), 0),
                    )
                )
            ).one()
            stats.total_conversations = int(totals[0] or 0)
            stats.total_messages = int(totals[1] or 0)
            stats.total_knowledge_items = int((await db.execute(select(func.count(KnowledgeItem.id)))).scalar() or 0)
            stats.total_products = int((await db.execute(select(func.count(Product.id)))).scalar() or 0)
            stats.total_users = int((await db.execute(select(func.count(User.id)))).scalar() or 0)

            today = utcnow().date()
            week_start = today - timedelta(days=today.weekday())
            month_start = today.replace(day=1)

            stats.conversations_today = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(StatisticsDaily.conversations), 0)).where(
                            StatisticsDaily.date == today
                        )
                    )
                ).scalar()
                or 0
            )
            stats.conversations_this_week = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(StatisticsDaily.conversations), 0)).where(
                            StatisticsDaily.date >= week_start,
                            StatisticsDaily.date <= today,
                        )
                    )
                ).scalar()
                or 0
            )
            stats.conversations_this_month = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(StatisticsDaily.conversations), 0)).where(
                            StatisticsDaily.date >= month_start,
                            StatisticsDaily.date <= today,
                        )
                    )
                ).scalar()
                or 0
            )

            try:
                from app.services.performance_service import get_performance_service

                perf = get_performance_service()
                chat_stat = perf.get_collector("chat_api").get_stats(last_n=100)
                stats.avg_response_time_ms = float(chat_stat.avg_duration) * 1000.0
                stats.success_rate = float(chat_stat.success_rate)
            except Exception:
                pass

        except Exception as exc:
            logger.exception("Failed to load overview stats: %s", exc)

        return stats

    @classmethod
    async def get_daily_stats(
        cls,
        db: AsyncSession,
        days: int = 7,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> List[DailyStats]:
        daily_stats: List[DailyStats] = []
        now = utcnow()

        try:
            if start_date and end_date:
                range_start_date = start_date
                range_end_date = end_date
            elif start_date or end_date:
                raise ValueError("start_date and end_date must be provided together")
            else:
                days = max(1, int(days))
                today = now.date()
                range_start_date = today - timedelta(days=days - 1)
                range_end_date = today

            if range_start_date > range_end_date:
                raise ValueError("start_date must be <= end_date")

            rows = (
                await db.execute(
                    select(
                        StatisticsDaily.date,
                        StatisticsDaily.conversations,
                        StatisticsDaily.messages,
                        StatisticsDaily.user_messages,
                        StatisticsDaily.assistant_messages,
                    )
                    .where(
                        StatisticsDaily.date >= range_start_date,
                        StatisticsDaily.date <= range_end_date,
                    )
                    .order_by(StatisticsDaily.date.asc())
                )
            ).all()
            row_map = {
                row_date: {
                    "conversations": int(conversations or 0),
                    "messages": int(messages or 0),
                    "user_messages": int(user_messages or 0),
                    "assistant_messages": int(assistant_messages or 0),
                }
                for row_date, conversations, messages, user_messages, assistant_messages in rows
            }

            cursor = range_start_date
            while cursor <= range_end_date:
                bucket = row_map.get(cursor, {})
                daily_stats.append(
                    DailyStats(
                        date=cursor.strftime("%Y-%m-%d"),
                        conversations=bucket.get("conversations", 0),
                        messages=bucket.get("messages", 0),
                        user_messages=bucket.get("user_messages", 0),
                        assistant_messages=bucket.get("assistant_messages", 0),
                    )
                )
                cursor += timedelta(days=1)

        except Exception as exc:
            logger.exception("Failed to load daily stats: %s", exc)

        return daily_stats

    @classmethod
    async def get_category_distribution(cls, db: AsyncSession) -> CategoryDistribution:
        distribution = CategoryDistribution()

        try:
            knowledge_result = await db.execute(
                select(KnowledgeItem.category, func.count(KnowledgeItem.id)).group_by(KnowledgeItem.category)
            )
            for category, count in knowledge_result.all():
                distribution.knowledge_categories[category or "Uncategorized"] = int(count or 0)

            product_result = await db.execute(
                select(Product.category, func.count(Product.id)).group_by(Product.category)
            )
            for category, count in product_result.all():
                distribution.product_categories[category or "Uncategorized"] = int(count or 0)

        except Exception as exc:
            logger.exception("Failed to load category distribution: %s", exc)

        return distribution

    @classmethod
    async def clear_all_statistics_data(cls, db: AsyncSession) -> Dict[str, int]:
        """Clear all persisted statistics counters."""
        snapshot = (
            await db.execute(
                select(
                    func.count(StatisticsDaily.date),
                    func.coalesce(func.sum(StatisticsDaily.conversations), 0),
                    func.coalesce(func.sum(StatisticsDaily.messages), 0),
                )
            )
        ).one()
        deleted_days = int(snapshot[0] or 0)
        deleted_conversations = int(snapshot[1] or 0)
        deleted_messages = int(snapshot[2] or 0)

        await db.execute(delete(StatisticsDaily))
        cls._question_counter.clear()
        await db.commit()
        return {
            "deleted_days": deleted_days,
            "deleted_conversations": deleted_conversations,
            "deleted_messages": deleted_messages,
        }

    @classmethod
    async def clear_statistics_data_by_range(
        cls,
        db: AsyncSession,
        start_date: date,
        end_date: date,
    ) -> Dict[str, int]:
        """Clear statistics counters in the given date range."""
        snapshot = (
            await db.execute(
                select(
                    func.count(StatisticsDaily.date),
                    func.coalesce(func.sum(StatisticsDaily.conversations), 0),
                    func.coalesce(func.sum(StatisticsDaily.messages), 0),
                ).where(
                    StatisticsDaily.date >= start_date,
                    StatisticsDaily.date <= end_date,
                )
            )
        ).one()
        deleted_days = int(snapshot[0] or 0)
        deleted_conversations = int(snapshot[1] or 0)
        deleted_messages = int(snapshot[2] or 0)

        await db.execute(
            delete(StatisticsDaily).where(
                StatisticsDaily.date >= start_date,
                StatisticsDaily.date <= end_date,
            )
        )
        await db.commit()
        return {
            "deleted_days": deleted_days,
            "deleted_conversations": deleted_conversations,
            "deleted_messages": deleted_messages,
        }

    @classmethod
    def record_question(cls, question: str):
        simplified = question.strip()[:50]
        if simplified:
            cls._question_counter[simplified] += 1

    @classmethod
    def get_top_questions(cls, limit: int = 10) -> List[Tuple[str, int]]:
        return cls._question_counter.most_common(limit)

    @classmethod
    async def export_report(cls, db: AsyncSession) -> str:
        stats = await cls.get_overview_stats(db)
        daily = await cls.get_daily_stats(db, 7)
        distribution = await cls.get_category_distribution(db)
        top_questions = cls.get_top_questions(10)

        lines = [
            "# Statistics Report",
            f"\nGenerated at: {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "\n## Overview",
            f"- Total conversations: {stats.total_conversations}",
            f"- Total messages: {stats.total_messages}",
            f"- Total knowledge items: {stats.total_knowledge_items}",
            f"- Total products: {stats.total_products}",
            f"- Total users: {stats.total_users}",
            "\n## Recent Activity",
            f"- Conversations today: {stats.conversations_today}",
            f"- Conversations this week: {stats.conversations_this_week}",
            f"- Conversations this month: {stats.conversations_this_month}",
        ]

        if distribution.knowledge_categories:
            lines.append("\n## Knowledge Categories")
            for category, count in sorted(distribution.knowledge_categories.items(), key=lambda x: -x[1]):
                lines.append(f"- {category}: {count}")

        if distribution.product_categories:
            lines.append("\n## Product Categories")
            for category, count in sorted(distribution.product_categories.items(), key=lambda x: -x[1]):
                lines.append(f"- {category}: {count}")

        if top_questions:
            lines.append("\n## Top Questions")
            for idx, (question, count) in enumerate(top_questions, 1):
                lines.append(f"{idx}. {question} ({count})")

        if daily:
            lines.append("\n## Daily Trend (Last 7 Days)")
            lines.append("| Date | Conversations | Messages | User Messages | Assistant Messages |")
            lines.append("|------|---------------|----------|---------------|--------------------|")
            for item in daily:
                lines.append(
                    f"| {item.date} | {item.conversations} | {item.messages} | {item.user_messages} | {item.assistant_messages} |"
                )

        return "\n".join(lines)

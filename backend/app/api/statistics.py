# -*- coding: utf-8 -*-
"""Statistics API Endpoints"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.dependencies import require_admin
from app.models.user import User
from app.services.statistics_service import StatisticsService
from app.schemas.statistics import (
    OverviewStatsResponse,
    DailyStatsResponse,
    DailyStatsItem,
    CategoryDistributionResponse,
    TopQuestionsResponse,
    TopQuestionItem,
    ExportReportResponse,
    StatisticsDataDeleteRequest,
    StatisticsDataDeleteResponse,
    StatisticsDataDeleteMode,
)
from app.utils.time import utcnow


router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/overview", response_model=OverviewStatsResponse)
async def get_overview_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    获取总体统计
    
    需要管理员权限
    
    返回:
    - 总对话数、消息数、知识库条目数、商品数、用户数
    - 今日/本周/本月对话数
    - 平均响应时间和成功率
    """
    stats = await StatisticsService.get_overview_stats(db)
    
    return OverviewStatsResponse(
        total_conversations=stats.total_conversations,
        total_messages=stats.total_messages,
        total_knowledge_items=stats.total_knowledge_items,
        total_products=stats.total_products,
        total_users=stats.total_users,
        conversations_today=stats.conversations_today,
        conversations_this_week=stats.conversations_this_week,
        conversations_this_month=stats.conversations_this_month,
        avg_response_time_ms=stats.avg_response_time_ms,
        success_rate=stats.success_rate,
    )


@router.get("/daily", response_model=DailyStatsResponse)
async def get_daily_stats(
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
    start_date: date | None = Query(default=None, description="开始日期（YYYY-MM-DD）"),
    end_date: date | None = Query(default=None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    获取每日统计
    
    需要管理员权限
    
    参数:
    - days: 统计天数（1-90天，默认7天）
    
    返回:
    - 每日对话数、消息数、用户消息数、助手消息数
    """
    if (start_date and not end_date) or (end_date and not start_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date 和 end_date 需要同时提供",
        )

    daily_stats = await StatisticsService.get_daily_stats(
        db,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    
    items = [
        DailyStatsItem(
            date=d.date,
            conversations=d.conversations,
            messages=d.messages,
            user_messages=d.user_messages,
            assistant_messages=d.assistant_messages
        )
        for d in daily_stats
    ]
    
    response_days = len(items) if (start_date and end_date) else days
    return DailyStatsResponse(items=items, days=response_days)


@router.get("/categories", response_model=CategoryDistributionResponse)
async def get_category_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    获取分类分布
    
    需要管理员权限
    
    返回:
    - 知识库分类分布
    - 商品分类分布
    """
    distribution = await StatisticsService.get_category_distribution(db)
    
    return CategoryDistributionResponse(
        knowledge_categories=distribution.knowledge_categories,
        product_categories=distribution.product_categories,
    )


@router.get("/top-questions", response_model=TopQuestionsResponse)
async def get_top_questions(
    limit: int = Query(default=10, ge=1, le=100, description="返回数量"),
    current_user: User = Depends(require_admin())
):
    """
    获取热门问题 Top N
    
    需要管理员权限
    
    参数:
    - limit: 返回数量（1-100，默认10）
    
    返回:
    - 热门问题列表（问题内容和出现次数）
    """
    top_questions = StatisticsService.get_top_questions(limit)
    
    items = [
        TopQuestionItem(question=q, count=c)
        for q, c in top_questions
    ]
    
    return TopQuestionsResponse(items=items)


@router.get("/export", response_model=ExportReportResponse)
async def export_statistics_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin())
):
    """
    导出统计报告
    
    需要管理员权限
    
    返回:
    - Markdown格式的统计报告
    - 生成时间
    """
    report_content = await StatisticsService.export_report(db)
    
    return ExportReportResponse(
        content=report_content,
        generated_at=utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )


@router.post("/data/delete", response_model=StatisticsDataDeleteResponse)
async def delete_statistics_data(
    request: StatisticsDataDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    删除统计数据（仅影响统计聚合，不删除业务数据）

    - reset_all: 清空全部统计聚合数据
    - date_range: 删除指定日期区间统计聚合数据
    """
    if request.mode == StatisticsDataDeleteMode.reset_all:
        result = await StatisticsService.clear_all_statistics_data(db)
        return StatisticsDataDeleteResponse(
            success=True,
            mode=request.mode,
            deleted_days=result["deleted_days"],
            deleted_conversations=result["deleted_conversations"],
            deleted_messages=result["deleted_messages"],
            message="统计数据已清空",
        )

    result = await StatisticsService.clear_statistics_data_by_range(
        db,
        start_date=request.start_date,  # validated by schema
        end_date=request.end_date,
    )
    return StatisticsDataDeleteResponse(
        success=True,
        mode=request.mode,
        deleted_days=result["deleted_days"],
        deleted_conversations=result["deleted_conversations"],
        deleted_messages=result["deleted_messages"],
        message="指定时间段统计数据已删除",
    )

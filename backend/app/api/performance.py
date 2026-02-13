# -*- coding: utf-8 -*-
"""Performance Monitoring API Endpoints"""
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_admin
from app.models.user import User
from app.services.performance_service import get_performance_service, MetricStats
from app.schemas.performance import (
    PerformanceSummaryResponse,
    PerformanceMetricsResponse,
    MetricStatsResponse,
    PerformanceClearResponse,
)
from app.utils.time import utcnow


router = APIRouter(prefix="/api/performance", tags=["performance"])


def metric_stats_to_response(stats: MetricStats) -> MetricStatsResponse:
    """Convert MetricStats to response model"""
    return MetricStatsResponse(
        name=stats.name,
        count=stats.count,
        success_rate=stats.success_rate,
        avg_duration=stats.avg_duration,
        min_duration=stats.min_duration,
        max_duration=stats.max_duration,
        p50_duration=stats.p50_duration,
        p95_duration=stats.p95_duration,
        p99_duration=stats.p99_duration,
        total_count=stats.total_count,
        total_success=stats.total_success,
    )


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    current_user: User = Depends(require_admin())
):
    """
    获取性能摘要
    
    需要管理员权限
    
    返回:
    - 运行时长
    - 总请求数
    - 总体成功率
    - 启动时间
    """
    service = get_performance_service()
    summary = service.get_summary()
    
    return PerformanceSummaryResponse(
        uptime_seconds=summary["uptime_seconds"],
        uptime_formatted=summary["uptime_formatted"],
        total_requests=summary["total_requests"],
        overall_success_rate=summary["overall_success_rate"],
        start_time=summary["start_time"],
    )


@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    last_n: int = Query(
        default=100, 
        ge=1, 
        le=1000, 
        description="统计最近N条记录"
    ),
    current_user: User = Depends(require_admin())
):
    """
    获取详细性能指标
    
    需要管理员权限
    
    参数:
    - last_n: 统计最近N条记录（1-1000，默认100）
    
    返回:
    - 性能摘要
    - 各指标详细统计（请求数、成功率、平均/最小/最大耗时、P50/P95/P99）
    """
    service = get_performance_service()
    summary = service.get_summary()
    all_stats = service.get_all_stats(last_n=last_n)
    
    metrics = {
        name: metric_stats_to_response(stats)
        for name, stats in all_stats.items()
    }
    
    return PerformanceMetricsResponse(
        summary=PerformanceSummaryResponse(
            uptime_seconds=summary["uptime_seconds"],
            uptime_formatted=summary["uptime_formatted"],
            total_requests=summary["total_requests"],
            overall_success_rate=summary["overall_success_rate"],
            start_time=summary["start_time"],
        ),
        metrics=metrics,
    )


@router.post("/clear", response_model=PerformanceClearResponse)
async def clear_performance_data(
    current_user: User = Depends(require_admin())
):
    """
    清空性能监控数据
    
    需要管理员权限
    
    返回:
    - 操作结果
    """
    service = get_performance_service()
    service.clear_all()
    
    return PerformanceClearResponse(
        success=True,
        message="性能监控数据已清空"
    )


@router.get("/export")
async def export_performance_report(
    current_user: User = Depends(require_admin())
):
    """
    导出性能报告
    
    需要管理员权限
    
    返回:
    - 纯文本格式的性能报告
    """
    from fastapi.responses import PlainTextResponse
    service = get_performance_service()
    report_content = service.export_report()
    
    return PlainTextResponse(content=report_content)

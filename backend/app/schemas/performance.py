# -*- coding: utf-8 -*-
"""Performance API Schemas"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class MetricStatsResponse(BaseModel):
    """指标统计响应"""
    name: str = Field(description="指标名称")
    count: int = Field(default=0, description="记录数")
    success_rate: float = Field(default=0.0, description="成功率")
    avg_duration: float = Field(default=0.0, description="平均耗时(秒)")
    min_duration: float = Field(default=0.0, description="最小耗时(秒)")
    max_duration: float = Field(default=0.0, description="最大耗时(秒)")
    p50_duration: float = Field(default=0.0, description="P50耗时(秒)")
    p95_duration: float = Field(default=0.0, description="P95耗时(秒)")
    p99_duration: float = Field(default=0.0, description="P99耗时(秒)")
    total_count: int = Field(default=0, description="累计总数")
    total_success: int = Field(default=0, description="累计成功数")


class PerformanceSummaryResponse(BaseModel):
    """性能摘要响应"""
    uptime_seconds: float = Field(description="运行时长(秒)")
    uptime_formatted: str = Field(description="格式化运行时长")
    total_requests: int = Field(description="总请求数")
    overall_success_rate: float = Field(description="总体成功率")
    start_time: str = Field(description="启动时间(ISO格式)")


class PerformanceMetricsResponse(BaseModel):
    """性能指标详情响应"""
    summary: PerformanceSummaryResponse = Field(description="性能摘要")
    metrics: Dict[str, MetricStatsResponse] = Field(
        default_factory=dict, 
        description="各指标统计"
    )


class PerformanceClearResponse(BaseModel):
    """清空性能数据响应"""
    success: bool = Field(description="是否成功")
    message: str = Field(description="消息")


class PerformanceExportResponse(BaseModel):
    """导出性能报告响应"""
    content: str = Field(description="报告内容")
    generated_at: str = Field(description="生成时间")

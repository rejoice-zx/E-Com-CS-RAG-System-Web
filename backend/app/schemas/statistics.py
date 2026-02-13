# -*- coding: utf-8 -*-
"""Statistics API Schemas"""
from enum import Enum
from datetime import date
from pydantic import BaseModel, Field
from pydantic import model_validator
from typing import Dict, List, Optional


class OverviewStatsResponse(BaseModel):
    """总体统计响应"""
    total_conversations: int = Field(description="总对话数")
    total_messages: int = Field(description="总消息数")
    total_knowledge_items: int = Field(description="知识库条目数")
    total_products: int = Field(description="商品数")
    total_users: int = Field(description="用户数")
    conversations_today: int = Field(description="今日对话数")
    conversations_this_week: int = Field(description="本周对话数")
    conversations_this_month: int = Field(description="本月对话数")
    avg_response_time_ms: float = Field(default=0.0, description="平均响应时间(ms)")
    success_rate: float = Field(default=0.0, description="成功率")


class DailyStatsItem(BaseModel):
    """每日统计项"""
    date: str = Field(description="日期 (YYYY-MM-DD)")
    conversations: int = Field(description="对话数")
    messages: int = Field(description="消息数")
    user_messages: int = Field(description="用户消息数")
    assistant_messages: int = Field(description="助手消息数")


class DailyStatsResponse(BaseModel):
    """每日统计响应"""
    items: List[DailyStatsItem] = Field(description="每日统计列表")
    days: int = Field(description="统计天数")


class CategoryDistributionResponse(BaseModel):
    """分类分布响应"""
    knowledge_categories: Dict[str, int] = Field(
        default_factory=dict, 
        description="知识库分类分布"
    )
    product_categories: Dict[str, int] = Field(
        default_factory=dict, 
        description="商品分类分布"
    )


class TopQuestionItem(BaseModel):
    """热门问题项"""
    question: str = Field(description="问题内容")
    count: int = Field(description="出现次数")


class TopQuestionsResponse(BaseModel):
    """热门问题响应"""
    items: List[TopQuestionItem] = Field(description="热门问题列表")


class ExportReportResponse(BaseModel):
    """导出报告响应"""
    content: str = Field(description="Markdown格式的报告内容")
    generated_at: str = Field(description="生成时间")


class StatisticsDataDeleteMode(str, Enum):
    reset_all = "reset_all"
    date_range = "date_range"


class StatisticsDataDeleteRequest(BaseModel):
    """统计数据删除请求"""
    mode: StatisticsDataDeleteMode = Field(description="删除模式：reset_all/date_range")
    start_date: Optional[date] = Field(default=None, description="开始日期（date_range 必填）")
    end_date: Optional[date] = Field(default=None, description="结束日期（date_range 必填）")

    @model_validator(mode="after")
    def validate_range(self):
        if self.mode == StatisticsDataDeleteMode.date_range:
            if not self.start_date or not self.end_date:
                raise ValueError("date_range mode requires start_date and end_date")
            if self.start_date > self.end_date:
                raise ValueError("start_date must be <= end_date")
        return self


class StatisticsDataDeleteResponse(BaseModel):
    """统计数据删除响应"""
    success: bool = Field(description="是否成功")
    mode: StatisticsDataDeleteMode = Field(description="删除模式")
    deleted_days: int = Field(default=0, description="删除的日期桶数量")
    deleted_conversations: int = Field(default=0, description="删除的对话累计数")
    deleted_messages: int = Field(default=0, description="删除的消息累计数")
    message: str = Field(description="结果说明")

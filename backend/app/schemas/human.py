# -*- coding: utf-8 -*-
"""Human Service Schemas - Pydantic models for human service API"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PendingConversationSummary(BaseModel):
    """待处理对话摘要"""
    id: str
    title: str
    status: str
    customer_id: Optional[str] = None
    updated_at: datetime
    message_count: Optional[int] = None
    wait_time_seconds: Optional[int] = None  # 等待时间（秒）

    model_config = {"from_attributes": True}


class PendingConversationListResponse(BaseModel):
    """待处理对话列表响应"""
    items: List[PendingConversationSummary]
    total: int
    page: int
    page_size: int


class HandlingConversationSummary(BaseModel):
    """正在处理的对话摘要"""
    id: str
    title: str
    status: str
    customer_id: Optional[str] = None
    human_agent_id: Optional[int] = None
    updated_at: datetime
    message_count: Optional[int] = None

    model_config = {"from_attributes": True}


class HandlingConversationListResponse(BaseModel):
    """正在处理的对话列表响应"""
    items: List[HandlingConversationSummary]
    total: int
    page: int
    page_size: int


class AcceptConversationResponse(BaseModel):
    """接入对话响应"""
    success: bool
    message: str
    conversation_id: str
    status: str
    agent_id: int


class CloseServiceResponse(BaseModel):
    """关闭服务响应"""
    success: bool
    message: str
    conversation_id: str
    status: str


class SendHumanMessageRequest(BaseModel):
    """客服发送消息请求"""
    content: str = Field(..., min_length=1, max_length=10000, description="消息内容")


class HumanMessageResponse(BaseModel):
    """人工消息响应"""
    id: int
    conversation_id: str
    role: str
    content: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class CancelTransferResponse(BaseModel):
    """取消转人工响应"""
    success: bool
    message: str
    conversation_id: str
    status: str


class ReturnToAIResponse(BaseModel):
    """返回AI模式响应"""
    success: bool
    message: str
    conversation_id: str
    status: str

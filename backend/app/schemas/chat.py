# -*- coding: utf-8 -*-
"""Chat Schemas - Pydantic models for chat API"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== 对话相关 ====================

class CreateConversationRequest(BaseModel):
    """创建对话请求"""
    title: Optional[str] = Field(None, max_length=200, description="对话标题")


class ConversationResponse(BaseModel):
    """对话响应"""
    id: str
    title: str
    status: str
    customer_id: Optional[str] = None
    human_agent_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """对话摘要（列表用）"""
    id: str
    title: str
    status: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    updated_at: datetime
    message_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    items: List[ConversationSummary]
    total: int
    page: int
    page_size: int


class UpdateConversationRequest(BaseModel):
    """更新对话请求"""
    title: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, pattern="^(normal|pending_human|human_handling|human_closed)$")


# ==================== 消息相关 ====================

class RAGTraceInfo(BaseModel):
    """RAG追踪信息"""
    query: str = ""
    rewritten_query: str = ""
    retrieved_items: List[Dict[str, Any]] = []
    context_text: str = ""
    confidence: float = 0.0
    search_method: str = "vector"
    final_prompt: str = ""
    
    model_config = {"extra": "ignore"}


class MessageResponse(BaseModel):
    """消息响应"""
    id: int
    conversation_id: str
    role: str
    content: str
    confidence: Optional[float] = None
    rag_trace: Optional[Dict[str, Any]] = None
    human_agent_name: Optional[str] = None
    is_deleted_by_user: bool = False
    deleted_by_customer_id: Optional[str] = None
    deleted_at: Optional[datetime] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    """消息列表响应"""
    items: List[MessageResponse]
    total: int
    page: int
    page_size: int


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    content: str = Field(..., min_length=1, max_length=10000, description="消息内容")


class SendMessageResponse(BaseModel):
    """发送消息响应（非流式）"""
    user_message: MessageResponse
    assistant_message: MessageResponse


# ==================== 转人工相关 ====================

class TransferHumanRequest(BaseModel):
    """转人工请求"""
    reason: Optional[str] = Field(None, max_length=500, description="转人工原因")


class TransferHumanResponse(BaseModel):
    """转人工响应"""
    success: bool
    message: str
    conversation_id: str
    status: str



# ==================== RAG调试相关 ====================

class DebugRAGRequest(BaseModel):
    """RAG调试请求"""
    query: str = Field(..., min_length=1, max_length=1000, description="查询内容")


class DebugRAGItem(BaseModel):
    """RAG调试检索结果项"""
    id: str
    question: str
    answer: str
    score: float
    category: str


class DebugRAGResponse(BaseModel):
    """RAG调试响应"""
    query: str = Field(description="原始查询")
    rewritten_query: str = Field(description="改写后的查询")
    retrieved_items: List[DebugRAGItem] = Field(description="检索到的知识条目")
    context_text: str = Field(description="构建的上下文文本")
    search_method: str = Field(description="检索方式")

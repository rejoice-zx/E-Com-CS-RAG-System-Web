# -*- coding: utf-8 -*-
"""Knowledge Schemas - Pydantic models for knowledge API"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ==================== 知识条目相关 ====================

class CreateKnowledgeRequest(BaseModel):
    """创建知识条目请求"""
    question: str = Field(..., min_length=1, max_length=2000, description="问题")
    answer: str = Field(..., min_length=1, max_length=10000, description="答案")
    keywords: Optional[List[str]] = Field(default=[], description="关键词列表")
    category: str = Field(default="通用", max_length=50, description="分类")
    score: float = Field(default=1.0, ge=0.0, le=10.0, description="权重分数")


class UpdateKnowledgeRequest(BaseModel):
    """更新知识条目请求"""
    question: Optional[str] = Field(None, min_length=1, max_length=2000)
    answer: Optional[str] = Field(None, min_length=1, max_length=10000)
    keywords: Optional[List[str]] = None
    category: Optional[str] = Field(None, max_length=50)
    score: Optional[float] = Field(None, ge=0.0, le=10.0)


class KnowledgeResponse(BaseModel):
    """知识条目响应"""
    id: str
    question: str
    answer: str
    keywords: List[str]
    category: str
    score: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KnowledgeListResponse(BaseModel):
    """知识列表响应"""
    items: List[KnowledgeResponse]
    total: int
    page: int
    page_size: int


# ==================== 导入导出相关 ====================

class ImportKnowledgeItem(BaseModel):
    """导入知识条目"""
    question: str
    answer: str
    keywords: Optional[List[str]] = []
    category: Optional[str] = "通用"
    score: Optional[float] = 1.0


class ImportKnowledgeRequest(BaseModel):
    """批量导入请求"""
    items: List[ImportKnowledgeItem]
    skip_duplicates: bool = Field(default=True, description="是否跳过重复项")


class ImportKnowledgeResponse(BaseModel):
    """批量导入响应"""
    success_count: int
    skip_count: int
    errors: List[str]


class ExportKnowledgeResponse(BaseModel):
    """导出响应"""
    items: List[dict]
    total: int


# ==================== 索引管理相关 ====================

class IndexStatusResponse(BaseModel):
    """索引状态响应"""
    count: int
    dimension: int
    embedding_model: Optional[str] = None
    embedding_available: bool
    embedding_dimension: Optional[int] = None
    needs_rebuild: bool = False
    rebuild_reason: Optional[str] = None


class RebuildIndexResponse(BaseModel):
    """重建索引响应"""
    success: bool
    success_count: int
    errors: List[str]
    message: str

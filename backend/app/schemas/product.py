# -*- coding: utf-8 -*-
"""Product Schemas - Pydantic models for product API"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== 商品相关 ====================

class CreateProductRequest(BaseModel):
    """创建商品请求"""
    name: str = Field(..., min_length=1, max_length=200, description="商品名称")
    price: float = Field(..., ge=0, description="价格")
    category: str = Field(default="通用", max_length=50, description="分类")
    description: str = Field(default="", max_length=5000, description="描述")
    specifications: Optional[Dict[str, str]] = Field(default={}, description="规格参数")
    stock: int = Field(default=0, ge=0, description="库存")
    keywords: Optional[List[str]] = Field(default=[], description="关键词列表")


class UpdateProductRequest(BaseModel):
    """更新商品请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    price: Optional[float] = Field(None, ge=0)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=5000)
    specifications: Optional[Dict[str, str]] = None
    stock: Optional[int] = Field(None, ge=0)
    keywords: Optional[List[str]] = None


class ProductResponse(BaseModel):
    """商品响应"""
    id: str
    name: str
    price: float
    category: str
    description: str
    specifications: Dict[str, str]
    stock: int
    keywords: List[str]
    is_out_of_stock: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    """商品列表响应"""
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int


# ==================== 导入导出相关 ====================

class ImportProductItem(BaseModel):
    """导入商品条目"""
    name: str
    price: float
    category: Optional[str] = "通用"
    description: Optional[str] = ""
    specifications: Optional[Dict[str, str]] = {}
    stock: Optional[int] = 0
    keywords: Optional[List[str]] = []


class ImportProductRequest(BaseModel):
    """批量导入请求"""
    items: List[ImportProductItem]
    skip_duplicates: bool = Field(default=True, description="是否跳过重复项")


class ImportProductResponse(BaseModel):
    """批量导入响应"""
    success_count: int
    skip_count: int
    errors: List[str]


class ExportProductResponse(BaseModel):
    """导出响应"""
    items: List[dict]
    total: int

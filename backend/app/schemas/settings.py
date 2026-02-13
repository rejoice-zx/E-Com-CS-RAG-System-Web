# -*- coding: utf-8 -*-
"""Settings API Schemas"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class LLMConfigRequest(BaseModel):
    """LLM配置请求"""
    provider: str = Field(description="提供商名称")
    api_key: Optional[str] = Field(default=None, description="API密钥")
    api_url: Optional[str] = Field(default=None, description="API地址")
    model: Optional[str] = Field(default=None, description="模型名称")


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    provider: str = Field(description="提供商名称")
    api_key_masked: str = Field(description="遮蔽的API密钥")
    api_url: str = Field(description="API地址")
    model: str = Field(description="模型名称")
    has_api_key: bool = Field(description="是否已配置API密钥")


class RAGConfigRequest(BaseModel):
    """RAG配置请求"""
    top_k: int = Field(default=5, ge=1, le=20, description="检索数量")
    similarity_threshold: float = Field(
        default=0.5, 
        ge=0.0, 
        le=1.0, 
        description="相似度阈值"
    )
    use_rewrite: bool = Field(default=True, description="是否使用查询改写")
    max_context_length: int = Field(
        default=2000, 
        ge=500, 
        le=10000, 
        description="最大上下文长度"
    )
    chunk_size: int = Field(default=500, ge=100, le=5000, description="分块大小")
    chunk_overlap: int = Field(default=50, ge=0, le=1000, description="分块重叠大小")


class RAGConfigResponse(BaseModel):
    """RAG配置响应"""
    top_k: int = Field(description="检索数量")
    similarity_threshold: float = Field(description="相似度阈值")
    use_rewrite: bool = Field(description="是否使用查询改写")
    max_context_length: int = Field(description="最大上下文长度")
    chunk_size: int = Field(default=500, description="分块大小")
    chunk_overlap: int = Field(default=50, description="分块重叠大小")


class EmbeddingConfigRequest(BaseModel):
    """Embedding配置请求"""
    provider: Optional[str] = Field(default=None, description="提供商名称")
    api_key: Optional[str] = Field(default=None, description="API密钥（为空则使用LLM的）")
    api_url: Optional[str] = Field(default=None, description="API地址")
    model: Optional[str] = Field(default=None, description="模型名称")
    dimension: Optional[int] = Field(default=None, ge=64, le=4096, description="向量维度")


class EmbeddingConfigResponse(BaseModel):
    """Embedding配置响应"""
    provider: str = Field(description="提供商名称")
    api_key_masked: str = Field(description="遮蔽的API密钥")
    api_url: str = Field(description="API地址")
    model: str = Field(description="模型名称")
    dimension: int = Field(description="向量维度")
    has_api_key: bool = Field(description="是否已配置API密钥")


class SettingsResponse(BaseModel):
    """设置响应"""
    llm: LLMConfigResponse = Field(description="LLM配置")
    embedding: EmbeddingConfigResponse = Field(description="Embedding配置")
    rag: RAGConfigResponse = Field(description="RAG配置")
    general: Optional['GeneralConfigResponse'] = Field(default=None, description="通用配置")


class GeneralConfigRequest(BaseModel):
    """通用配置请求"""
    timezone: Optional[str] = Field(default=None, description="时区，如 Asia/Shanghai")


class GeneralConfigResponse(BaseModel):
    """通用配置响应"""
    timezone: str = Field(default="Asia/Shanghai", description="时区")


class SettingsUpdateRequest(BaseModel):
    """设置更新请求"""
    llm: Optional[LLMConfigRequest] = Field(default=None, description="LLM配置")
    embedding: Optional[EmbeddingConfigRequest] = Field(default=None, description="Embedding配置")
    rag: Optional[RAGConfigRequest] = Field(default=None, description="RAG配置")
    general: Optional[GeneralConfigRequest] = Field(default=None, description="通用配置")


class LLMProviderInfo(BaseModel):
    """LLM提供商信息"""
    name: str = Field(description="提供商标识")
    display_name: str = Field(description="显示名称")
    default_api_url: str = Field(description="默认API地址")
    default_model: str = Field(description="默认模型")
    supported_models: List[str] = Field(description="支持的模型列表")


class LLMProvidersResponse(BaseModel):
    """LLM提供商列表响应"""
    providers: List[LLMProviderInfo] = Field(description="提供商列表")


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    provider: str = Field(description="提供商名称")
    api_key: Optional[str] = Field(default=None, description="API密钥（可选，不传则使用已保存的）")
    api_url: Optional[str] = Field(default=None, description="API地址")
    model: Optional[str] = Field(default=None, description="模型名称")


class TestConnectionResponse(BaseModel):
    """测试连接响应"""
    success: bool = Field(description="是否成功")
    message: str = Field(description="消息")

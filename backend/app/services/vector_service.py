# -*- coding: utf-8 -*-
"""
向量存储服务模块 - 封装FAISS向量存储和Embedding服务

功能:
- 复用现有core/vector_store.py和core/embedding.py
- 提供异步调用接口
- 支持向量索引管理
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# 延迟导入core模块
_vector_store = None
_embedding_client = None
_executor = ThreadPoolExecutor(max_workers=4)


def _get_vector_store():
    """获取向量存储实例（延迟加载）"""
    global _vector_store
    if _vector_store is None:
        from app.core.vector_store import VectorStore
        _vector_store = VectorStore()
    return _vector_store


def _get_embedding_client():
    """获取Embedding客户端实例（延迟加载）"""
    global _embedding_client
    if _embedding_client is None:
        from app.core.embedding import EmbeddingClient
        _embedding_client = EmbeddingClient()
    return _embedding_client


class VectorService:
    """向量服务类 - 异步封装"""
    
    def __init__(self):
        """初始化向量服务"""
        self._loop = None
        self._config_synced = False
    
    def _get_loop(self):
        """获取事件循环"""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()
    
    async def sync_config_from_db(self, db) -> bool:
        """从数据库同步Embedding配置到EmbeddingClient
        
        解决配置双轨制问题：前端设置保存在数据库，但EmbeddingClient读的是文件配置。
        此方法将数据库中的Embedding配置注入到EmbeddingClient。
        
        Args:
            db: 数据库会话
            
        Returns:
            是否成功同步且配置可用
        """
        try:
            from app.services.settings_service import SettingsService
            embedding_config = await SettingsService.get_embedding_config(db)
            
            client = _get_embedding_client()
            
            # 确定API密钥：Embedding独立配置 > LLM共享配置
            api_key = embedding_config.api_key
            if not api_key:
                # 尝试使用LLM的API密钥
                llm_config = await SettingsService.get_llm_config(db)
                api_key = llm_config.api_key
            
            api_url = embedding_config.api_url
            if not api_url:
                llm_config = await SettingsService.get_llm_config(db)
                api_url = llm_config.api_url
            
            client.configure(
                api_key=api_key or None,
                api_url=api_url or None,
                model=embedding_config.model or None,
                dimension=embedding_config.dimension or None,
            )
            
            self._config_synced = True
            logger.info("已从数据库同步Embedding配置, model=%s, has_key=%s", 
                       embedding_config.model, bool(api_key))
            return bool(api_key)
        except Exception as e:
            logger.error("同步Embedding配置失败: %s", str(e))
            return False
    
    async def embed_text(self, text: str) -> Optional[List[float]]:
        """
        将文本向量化（异步）
        
        Args:
            text: 要向量化的文本
        
        Returns:
            向量列表，失败返回None
        """
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            loop = self._get_loop()
            client = _get_embedding_client()
            result = await loop.run_in_executor(_executor, client.embed_text, text)
            if result is None:
                success = False
            return result
        except Exception:
            success = False
            raise
        finally:
            duration = _time.perf_counter() - start
            perf.record("embedding_api", duration, success)
    
    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量将文本向量化（异步）
        
        Args:
            texts: 要向量化的文本列表
        
        Returns:
            向量列表的列表
        """
        loop = self._get_loop()
        client = _get_embedding_client()
        return await loop.run_in_executor(_executor, client.embed_texts, texts)
    
    async def add_vector(self, item_id: str, vector: List[float]) -> bool:
        """
        添加向量到索引（异步）
        
        Args:
            item_id: 知识条目ID
            vector: 向量
        
        Returns:
            是否成功
        """
        loop = self._get_loop()
        store = _get_vector_store()
        return await loop.run_in_executor(_executor, store.add_vector, item_id, vector)
    
    async def add_item(self, item_id: str, text: str) -> bool:
        """
        添加文本到向量索引（先向量化再添加）
        
        Args:
            item_id: 知识条目ID
            text: 文本内容
        
        Returns:
            是否成功
        """
        vector = await self.embed_text(text)
        if vector is None:
            return False
        return await self.add_vector(item_id, vector)
    
    async def remove_vector(self, item_id: str) -> bool:
        """
        从索引中删除向量（异步）
        
        Args:
            item_id: 知识条目ID
        
        Returns:
            是否成功
        """
        loop = self._get_loop()
        store = _get_vector_store()
        return await loop.run_in_executor(_executor, store.remove_vector, item_id)
    
    async def remove_vectors_by_prefix(self, prefix: str) -> int:
        """
        按前缀删除向量（异步）
        
        Args:
            prefix: ID前缀
        
        Returns:
            删除的数量
        """
        loop = self._get_loop()
        store = _get_vector_store()
        return await loop.run_in_executor(_executor, store.remove_vectors_by_prefix, prefix)
    
    async def search(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        搜索相似向量（异步）
        
        Args:
            query_vector: 查询向量
            top_k: 返回数量
        
        Returns:
            [(知识ID, 相似度分数), ...]
        """
        loop = self._get_loop()
        store = _get_vector_store()
        return await loop.run_in_executor(_executor, store.search, query_vector, top_k)
    
    async def search_by_text(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        通过文本搜索相似内容（异步）
        
        Args:
            query: 查询文本
            top_k: 返回数量
        
        Returns:
            [(知识ID, 相似度分数), ...]
        """
        vector = await self.embed_text(query)
        if vector is None:
            return []
        return await self.search(vector, top_k)
    
    async def save(self) -> None:
        """保存索引到磁盘（异步）"""
        loop = self._get_loop()
        store = _get_vector_store()
        await loop.run_in_executor(_executor, store.save)
    
    async def clear(self) -> None:
        """清空索引（异步）"""
        loop = self._get_loop()
        store = _get_vector_store()
        await loop.run_in_executor(_executor, store.clear)
    
    def get_index_info(self) -> Dict[str, Any]:
        """获取索引信息（同步）"""
        store = _get_vector_store()
        return store.get_index_info()
    
    def needs_rebuild(self, current_embedding_model: str = None) -> Tuple[bool, str]:
        """检查是否需要重建索引（同步）"""
        store = _get_vector_store()
        return store.needs_rebuild(current_embedding_model)
    
    def check_dimension_compatibility(self, expected_dimension: int) -> Tuple[bool, str]:
        """检查向量维度兼容性（同步）"""
        store = _get_vector_store()
        return store.check_dimension_compatibility(expected_dimension)
    
    @property
    def count(self) -> int:
        """获取向量数量"""
        store = _get_vector_store()
        return store.count
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        store = _get_vector_store()
        return store.dimension
    
    @property
    def embedding_model(self) -> Optional[str]:
        """获取当前embedding模型"""
        store = _get_vector_store()
        return store.embedding_model
    
    def has_item(self, item_id: str) -> bool:
        """检查是否存在某知识的向量"""
        store = _get_vector_store()
        return store.has_item(item_id)
    
    def is_embedding_available(self) -> bool:
        """检查Embedding服务是否可用"""
        client = _get_embedding_client()
        return client.is_available()
    
    @property
    def embedding_dimension(self) -> int:
        """获取Embedding维度"""
        client = _get_embedding_client()
        return client.dimension


class EmbeddingService:
    """Embedding服务类 - 异步封装"""
    
    async def embed_text(self, text: str) -> Optional[List[float]]:
        """将文本向量化（异步）"""
        loop = asyncio.get_running_loop()
        client = _get_embedding_client()
        return await loop.run_in_executor(_executor, client.embed_text, text)
    
    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """批量将文本向量化（异步）"""
        loop = asyncio.get_running_loop()
        client = _get_embedding_client()
        return await loop.run_in_executor(_executor, client.embed_texts, texts)
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        client = _get_embedding_client()
        return client.is_available()
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        client = _get_embedding_client()
        return client.dimension

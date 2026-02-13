# -*- coding: utf-8 -*-
"""
Embedding模块 - 调用硅基流动API进行文本向量化

优化内容 (v2.2.0):
- 细化异常处理
- 添加指数退避重试机制
- 集成API限流保护
- 批处理失败时继续处理其他批次

优化内容 (v2.3.0):
- 支持外部配置注入（数据库配置优先于文件配置）
- 统一API密钥/模型/地址的获取逻辑
"""

import time
import requests
import logging
from typing import List, Optional, Tuple
from requests.exceptions import RequestException, Timeout, ConnectionError
from app.core.config import Config


logger = logging.getLogger(__name__)


def exponential_backoff(attempt: int, base_delay: float = 1.0) -> float:
    """计算指数退避延迟时间"""
    return min(base_delay * (2 ** attempt), 30.0)


class EmbeddingClient:
    """Embedding客户端 - 支持硅基流动API"""
    
    _instance = None
    
    # 支持的Embedding模型映射
    MODEL_MAPPING = {
        "bge-large-zh": "BAAI/bge-large-zh-v1.5",
        "m3e-base": "BAAI/bge-m3",
        "text-embedding-ada-002": "BAAI/bge-large-zh-v1.5"  # 使用bge作为替代
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.config = Config()
        self._dimension = 1024  # bge-large-zh-v1.5 维度
        
        # 外部注入的配置（优先级高于默认配置）
        self._override_api_key: Optional[str] = None
        self._override_api_url: Optional[str] = None
        self._override_model: Optional[str] = None
        self._override_dimension: Optional[int] = None
        
        # 重试配置
        self._max_retries = 3
        self._base_delay = 1.0
    
    def configure(self, api_key: str = None, api_url: str = None, 
                  model: str = None, dimension: int = None):
        """注入外部配置（来自数据库），优先级高于默认值和环境变量
        
        Args:
            api_key: API密钥
            api_url: API地址
            model: 模型名称（如 BAAI/bge-large-zh-v1.5）
            dimension: 向量维度
        """
        if api_key is not None:
            self._override_api_key = api_key
        if api_url is not None:
            self._override_api_url = api_url
        if model is not None:
            self._override_model = model
        if dimension is not None:
            self._override_dimension = dimension
            self._dimension = dimension
    
    def _get_api_key(self) -> str:
        """获取API密钥（优先使用外部注入的配置）"""
        if self._override_api_key:
            return self._override_api_key
        return self.config.get("api_key", "")
    
    def _get_api_url(self) -> str:
        """获取API地址（优先使用外部注入的配置）"""
        if self._override_api_url:
            return self._override_api_url
        return self.config.get("api_base_url", "") or "https://api.siliconflow.cn/v1"
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        return self._dimension
    
    def _get_model_name(self) -> str:
        """获取实际的模型名称"""
        if self._override_model:
            return self._override_model
        ui_model = self.config.get("embedding_model", "bge-large-zh")
        return self.MODEL_MAPPING.get(ui_model, "BAAI/bge-large-zh-v1.5")
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        将单个文本向量化
        
        Args:
            text: 要向量化的文本
        
        Returns:
            向量列表，失败返回None
        """
        result = self.embed_texts([text])
        if result and len(result) > 0:
            return result[0]
        return None
    
    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量将文本向量化（自动分批处理，失败时继续处理其他批次）
        
        Args:
            texts: 要向量化的文本列表
        
        Returns:
            向量列表的列表，部分失败时对应位置为None
        """
        if not texts:
            return []
        
        api_key = self._get_api_key()
        if not api_key:
            logger.warning("未配置API密钥，无法进行向量化")
            return None
        
        # API最大批次大小
        BATCH_SIZE = 32
        
        # 如果数量小于批次大小，直接调用
        if len(texts) <= BATCH_SIZE:
            return self._embed_batch_with_retry(texts)
        
        # 分批处理
        all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
        success_count = 0
        fail_count = 0
        
        logger.info("共 %s 条文本，分 %s 批处理（每批最多 %s 条）", len(texts), total_batches, BATCH_SIZE)
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(texts))
            batch = texts[start_idx:end_idx]
            batch_num = batch_idx + 1
            
            logger.info("处理批次 %s/%s", batch_num, total_batches)
            
            embeddings = self._embed_batch_with_retry(batch)
            
            if embeddings is None:
                logger.warning("批次 %s 失败，跳过继续处理", batch_num)
                fail_count += len(batch)
            else:
                for i, emb in enumerate(embeddings):
                    all_embeddings[start_idx + i] = emb
                success_count += len(embeddings)
        
        logger.info("向量化完成: 成功 %s, 失败 %s", success_count, fail_count)
        
        if success_count == 0:
            return None
        
        return all_embeddings
    
    def _embed_batch_with_retry(self, texts: List[str]) -> Optional[List[List[float]]]:
        """带重试的批量向量化"""
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                result = self._embed_batch(texts)
                if result is not None:
                    return result
            except Exception as e:
                last_error = e
                logger.warning("Embedding批次处理失败（尝试 %d/%d）: %s", 
                             attempt + 1, self._max_retries, str(e))
            
            if attempt < self._max_retries - 1:
                delay = exponential_backoff(attempt, self._base_delay)
                time.sleep(delay)
        
        if last_error:
            logger.error("Embedding批次处理最终失败: %s", str(last_error))
        return None
    
    def _embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """处理单个批次的embedding"""
        api_key = self._get_api_key()
        api_base_url = self._get_api_url()
        model = self._get_model_name()
        
        url = f"{api_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "input": texts,
            "encoding_format": "float"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                embeddings = [item["embedding"] for item in result["data"]]
                if embeddings and len(embeddings) > 0:
                    self._dimension = len(embeddings[0])
                return embeddings
            elif response.status_code == 401:
                logger.error("Embedding API密钥无效")
                return None
            elif response.status_code == 429:
                logger.warning("Embedding API限流，稍后重试")
                raise Exception("API限流")
            elif response.status_code >= 500:
                logger.warning("Embedding API服务器错误: %s", response.status_code)
                raise Exception(f"服务器错误 {response.status_code}")
            else:
                logger.warning("Embedding API调用失败: %s - %s", response.status_code, response.text)
                return None
        except Timeout:
            logger.warning("Embedding API调用超时")
            raise Exception("请求超时")
        except ConnectionError:
            logger.warning("Embedding API网络连接失败")
            raise Exception("网络连接失败")
        except RequestException as e:
            logger.warning("Embedding API网络错误: %s", str(e))
            raise Exception(f"网络错误: {str(e)}")
    
    def is_available(self) -> bool:
        """检查Embedding服务是否可用"""
        api_key = self._get_api_key()
        return bool(api_key)

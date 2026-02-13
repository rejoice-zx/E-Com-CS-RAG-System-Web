# -*- coding: utf-8 -*-
"""
设置管理服务模块

功能:
- 系统设置的读取和更新
- LLM提供商配置
- API密钥加密存储
- API连接测试
"""

import json
import logging
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.models.settings import SystemSettings
from app.services.llm_service import (
    get_all_providers,
    get_provider,
    LLMServiceError,
)
from app.config import settings as app_settings
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


# 加密密钥派生
def _get_encryption_key() -> bytes:
    """从JWT密钥派生加密密钥"""
    salt = b'settings_encryption_salt'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(
        kdf.derive(app_settings.JWT_SECRET_KEY.encode())
    )
    return key


def _encrypt_value(value: str) -> str:
    """加密敏感值"""
    if not value:
        return value
    try:
        f = Fernet(_get_encryption_key())
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error("加密失败: %s", str(e))
        return value


def _decrypt_value(encrypted: str) -> str:
    """解密敏感值"""
    if not encrypted:
        return encrypted
    try:
        f = Fernet(_get_encryption_key())
        return f.decrypt(encrypted.encode()).decode()
    except Exception as e:
        logger.error("解密失败: %s", str(e))
        return encrypted


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "siliconflow"
    api_key: str = ""
    api_url: str = ""
    model: str = ""


@dataclass
class EmbeddingConfig:
    """Embedding配置"""
    provider: str = "siliconflow"  # 使用与LLM相同的提供商
    api_key: str = ""  # 可以单独配置，为空则使用LLM的api_key
    api_url: str = ""
    model: str = "BAAI/bge-large-zh-v1.5"
    dimension: int = 1024


@dataclass
class RAGConfig:
    """RAG配置"""
    top_k: int = 5
    similarity_threshold: float = 0.5
    use_rewrite: bool = True
    max_context_length: int = 2000
    chunk_size: int = 500
    chunk_overlap: int = 50


@dataclass
class GeneralConfig:
    """通用配置"""
    timezone: str = "Asia/Shanghai"


@dataclass
class SystemConfig:
    """系统配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)


class SettingsService:
    """设置管理服务"""
    
    # 设置键名
    KEY_LLM_CONFIG = "llm_config"
    KEY_EMBEDDING_CONFIG = "embedding_config"
    KEY_RAG_CONFIG = "rag_config"
    KEY_GENERAL_CONFIG = "general_config"
    
    # 敏感字段（需要加密）
    SENSITIVE_FIELDS = ["api_key"]
    
    @classmethod
    async def get_setting(
        cls, 
        db: AsyncSession, 
        key: str
    ) -> Optional[str]:
        """获取单个设置值
        
        Args:
            db: 数据库会话
            key: 设置键名
            
        Returns:
            设置值或None
        """
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None
    
    @classmethod
    async def set_setting(
        cls, 
        db: AsyncSession, 
        key: str, 
        value: str
    ):
        """设置单个值
        
        Args:
            db: 数据库会话
            key: 设置键名
            value: 设置值
        """
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            setting.value = value
            setting.updated_at = utcnow()
        else:
            setting = SystemSettings(key=key, value=value)
            db.add(setting)
        
        await db.commit()
    
    @classmethod
    async def get_llm_config(cls, db: AsyncSession) -> LLMConfig:
        """获取LLM配置
        
        Args:
            db: 数据库会话
            
        Returns:
            LLMConfig: LLM配置
        """
        value = await cls.get_setting(db, cls.KEY_LLM_CONFIG)
        
        if not value:
            return LLMConfig()
        
        try:
            data = json.loads(value)
            # 解密API密钥
            if "api_key" in data and data["api_key"]:
                data["api_key"] = _decrypt_value(data["api_key"])
            return LLMConfig(**data)
        except Exception as e:
            logger.error("解析LLM配置失败: %s", str(e))
            return LLMConfig()
    
    @classmethod
    async def set_llm_config(
        cls, 
        db: AsyncSession, 
        config: LLMConfig
    ):
        """设置LLM配置
        
        Args:
            db: 数据库会话
            config: LLM配置
        """
        data = asdict(config)
        # 加密API密钥
        if data.get("api_key"):
            data["api_key"] = _encrypt_value(data["api_key"])
        
        await cls.set_setting(db, cls.KEY_LLM_CONFIG, json.dumps(data))

    @classmethod
    async def get_embedding_config(cls, db: AsyncSession) -> EmbeddingConfig:
        """获取Embedding配置
        
        Args:
            db: 数据库会话
            
        Returns:
            EmbeddingConfig: Embedding配置
        """
        value = await cls.get_setting(db, cls.KEY_EMBEDDING_CONFIG)
        
        if not value:
            return EmbeddingConfig()
        
        try:
            data = json.loads(value)
            # 解密API密钥
            if "api_key" in data and data["api_key"]:
                data["api_key"] = _decrypt_value(data["api_key"])
            return EmbeddingConfig(**data)
        except Exception as e:
            logger.error("解析Embedding配置失败: %s", str(e))
            return EmbeddingConfig()
    
    @classmethod
    async def set_embedding_config(
        cls, 
        db: AsyncSession, 
        config: EmbeddingConfig
    ):
        """设置Embedding配置
        
        Args:
            db: 数据库会话
            config: Embedding配置
        """
        data = asdict(config)
        # 加密API密钥
        if data.get("api_key"):
            data["api_key"] = _encrypt_value(data["api_key"])
        
        await cls.set_setting(db, cls.KEY_EMBEDDING_CONFIG, json.dumps(data))

    @classmethod
    async def get_rag_config(cls, db: AsyncSession) -> RAGConfig:
        """获取RAG配置
        
        Args:
            db: 数据库会话
            
        Returns:
            RAGConfig: RAG配置
        """
        value = await cls.get_setting(db, cls.KEY_RAG_CONFIG)
        
        if not value:
            return RAGConfig()
        
        try:
            data = json.loads(value)
            return RAGConfig(**data)
        except Exception as e:
            logger.error("解析RAG配置失败: %s", str(e))
            return RAGConfig()
    
    @classmethod
    async def set_rag_config(
        cls, 
        db: AsyncSession, 
        config: RAGConfig
    ):
        """设置RAG配置
        
        Args:
            db: 数据库会话
            config: RAG配置
        """
        await cls.set_setting(
            db, 
            cls.KEY_RAG_CONFIG, 
            json.dumps(asdict(config))
        )
    
    @classmethod
    async def get_all_settings(cls, db: AsyncSession) -> SystemConfig:
        """获取所有设置
        
        Args:
            db: 数据库会话
            
        Returns:
            SystemConfig: 系统配置
        """
        llm_config = await cls.get_llm_config(db)
        embedding_config = await cls.get_embedding_config(db)
        rag_config = await cls.get_rag_config(db)
        general_config = await cls.get_general_config(db)
        
        return SystemConfig(llm=llm_config, embedding=embedding_config, rag=rag_config, general=general_config)
    
    @classmethod
    async def get_general_config(cls, db: AsyncSession) -> GeneralConfig:
        """获取通用配置"""
        value = await cls.get_setting(db, cls.KEY_GENERAL_CONFIG)
        if not value:
            return GeneralConfig()
        try:
            data = json.loads(value)
            return GeneralConfig(**data)
        except Exception as e:
            logger.error("解析通用配置失败: %s", str(e))
            return GeneralConfig()

    @classmethod
    async def set_general_config(cls, db: AsyncSession, config: GeneralConfig):
        """设置通用配置"""
        await cls.set_setting(db, cls.KEY_GENERAL_CONFIG, json.dumps(asdict(config)))

    @classmethod
    async def update_settings(
        cls, 
        db: AsyncSession, 
        llm_config: Optional[LLMConfig] = None,
        embedding_config: Optional[EmbeddingConfig] = None,
        rag_config: Optional[RAGConfig] = None,
        general_config: Optional[GeneralConfig] = None,
    ):
        """更新设置
        
        Args:
            db: 数据库会话
            llm_config: LLM配置（可选）
            embedding_config: Embedding配置（可选）
            rag_config: RAG配置（可选）
        """
        if llm_config:
            await cls.set_llm_config(db, llm_config)
        if embedding_config:
            await cls.set_embedding_config(db, embedding_config)
        if rag_config:
            await cls.set_rag_config(db, rag_config)
        if general_config:
            await cls.set_general_config(db, general_config)
    
    @classmethod
    def get_llm_providers(cls) -> List[Dict[str, Any]]:
        """获取所有LLM提供商信息
        
        Returns:
            List[Dict]: 提供商列表
        """
        return get_all_providers()
    
    @classmethod
    async def test_llm_connection(
        cls,
        provider: str,
        api_key: str,
        api_url: Optional[str] = None,
        model: Optional[str] = None
    ) -> tuple:
        """测试LLM API连接
        
        Args:
            provider: 提供商名称
            api_key: API密钥
            api_url: API地址（可选）
            model: 模型名称（可选）
            
        Returns:
            tuple: (成功标志, 消息)
        """
        try:
            provider_class = get_provider(provider)
            instance = provider_class(
                api_key=api_key,
                api_url=api_url,
                model=model,
                timeout=15
            )
            return await instance.test_connection()
        except ValueError as e:
            return False, f"未知的提供商: {provider}"
        except LLMServiceError as e:
            return False, str(e)
        except Exception as e:
            return False, f"连接测试失败: {str(e)}"
    
    @classmethod
    def mask_api_key(cls, api_key: str) -> str:
        """遮蔽API密钥（用于显示）
        
        Args:
            api_key: API密钥
            
        Returns:
            str: 遮蔽后的密钥
        """
        if not api_key or len(api_key) < 8:
            return "****"
        return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]

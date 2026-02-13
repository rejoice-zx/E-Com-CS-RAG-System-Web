"""Application Configuration"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os

DEFAULT_JWT_SECRET = "your-secret-key-change-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
    
    # Application
    APP_NAME: str = "智能电商客服RAG系统"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"
    
    # JWT Authentication
    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    
    # Paths
    DATA_DIR: str = "./data"
    LOGS_DIR: str = "./logs"


settings = Settings()


def is_insecure_jwt_secret(secret: str) -> bool:
    normalized = (secret or "").strip()
    return not normalized or normalized == DEFAULT_JWT_SECRET


def is_production_environment() -> bool:
    app_env = os.getenv("APP_ENV", os.getenv("ENV", "")).strip().lower()
    return app_env in {"prod", "production"}

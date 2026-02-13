"""FastAPI Application Entry Point"""
import os
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings, is_insecure_jwt_secret, is_production_environment
from app.database import init_db


class _TzAwareFormatter(logging.Formatter):
    """日志格式化器：使用系统设置中的时区输出时间戳"""

    def __init__(self, fmt=None, datefmt=None, tz_name: str = "Asia/Shanghai"):
        super().__init__(fmt, datefmt)
        self._tz = self._resolve_tz(tz_name)

    @staticmethod
    def _resolve_tz(tz_name: str):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tz_name)
        except Exception:
            return timezone.utc

    def set_timezone(self, tz_name: str):
        self._tz = self._resolve_tz(tz_name)

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


# 全局 formatter 实例，供 lifespan 和 settings API 更新时区
_log_formatter = _TzAwareFormatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    tz_name="Asia/Shanghai",
)


def get_log_formatter() -> _TzAwareFormatter:
    """获取全局日志格式化器（供外部模块更新时区）"""
    return _log_formatter


def setup_logging():
    """配置日志写入文件"""
    log_dir = settings.LOGS_DIR
    if not os.path.isabs(log_dir):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, log_dir)
    os.makedirs(log_dir, exist_ok=True)

    # 应用日志 - app.log (INFO+)
    app_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(_log_formatter)

    # 错误日志 - error.log (ERROR+)
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(_log_formatter)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_log_formatter)

    # 配置根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)


setup_logging()
from app.middleware.rate_limit import RateLimitMiddleware
from app.api import (
    auth_router,
    chat_router,
    knowledge_router,
    product_router,
    human_router,
    statistics_router,
    performance_router,
    logs_router,
    settings_router,
    backup_router,
)
from app.api.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup: Initialize database
    await init_db()

    # 从数据库同步时区设置到日志格式化器
    try:
        from app.database import get_db as _get_db_gen
        async for db in _get_db_gen():
            from app.services.settings_service import SettingsService
            general = await SettingsService.get_general_config(db)
            if general.timezone:
                _log_formatter.set_timezone(general.timezone)
            break
    except Exception:
        pass  # 首次启动数据库可能为空，使用默认时区
    
    # Security check for JWT secret key
    _logger = logging.getLogger(__name__)
    if is_insecure_jwt_secret(settings.JWT_SECRET_KEY):
        if is_production_environment():
            raise RuntimeError(
                "JWT_SECRET_KEY is insecure in production environment. "
                "Set a strong JWT_SECRET_KEY via environment variables before startup."
            )
        _logger.warning(
            "JWT_SECRET_KEY is still using the default insecure value. "
            "Set a strong key in .env before deploying to production."
        )
    
    yield
    # Shutdown: Cleanup if needed


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="智能电商客服RAG系统 - Vue3前后端分离架构",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Include API routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(product_router)
app.include_router(human_router)
app.include_router(statistics_router)
app.include_router(performance_router)
app.include_router(logs_router)
app.include_router(settings_router)
app.include_router(backup_router)
app.include_router(users_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# API Routes Package
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.api.product import router as product_router
from app.api.human import router as human_router
from app.api.statistics import router as statistics_router
from app.api.performance import router as performance_router
from app.api.logs import router as logs_router
from app.api.settings import router as settings_router
from app.api.backup import router as backup_router

__all__ = [
    "auth_router",
    "chat_router",
    "knowledge_router",
    "product_router",
    "human_router",
    "statistics_router",
    "performance_router",
    "logs_router",
    "settings_router",
    "backup_router",
]

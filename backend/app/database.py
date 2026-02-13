"""Database Configuration and Connection Management"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from datetime import date, datetime
import os

from app.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy Declarative Base"""
    pass


# Create async engine with connection pool
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    # SQLite specific settings for async
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database - create all tables and default admin user"""
    # Ensure data directory exists
    data_dir = os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    
    # Import models to register them with Base
    from app.models import user, conversation, knowledge, product, statistics
    from app.models.user import User
    from app.models.conversation import Conversation, Message
    from app.models.statistics import StatisticsDaily, StatisticsMeta
    from app.services.auth_service import AuthService
    from sqlalchemy import case, select, func
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Add new columns if they don't exist (for existing databases)
        from sqlalchemy import text, inspect as sa_inspect
        
        def _add_missing_columns(connection):
            inspector = sa_inspect(connection)
            
            # Check conversations table for customer_id column
            conv_columns = [c["name"] for c in inspector.get_columns("conversations")]
            if "customer_id" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN customer_id VARCHAR(64) NOT NULL DEFAULT 'anonymous'"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_customer_id ON conversations(customer_id)"
                ))
            if "temp_session_id" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN temp_session_id VARCHAR(128)"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_temp_session_id ON conversations(temp_session_id)"
                ))
            if "temp_device_id" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN temp_device_id VARCHAR(128)"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_temp_device_id ON conversations(temp_device_id)"
                ))
            if "is_deleted_by_user" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN is_deleted_by_user BOOLEAN NOT NULL DEFAULT 0"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_is_deleted_by_user ON conversations(is_deleted_by_user)"
                ))
            if "deleted_by_customer_id" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN deleted_by_customer_id VARCHAR(64)"
                ))
            if "deleted_at" not in conv_columns:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN deleted_at DATETIME"
                ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_status_updated_at ON conversations(status, updated_at)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_created_at ON conversations(created_at)"
            ))
            
            # Check messages table for human_agent_name column
            msg_columns = [c["name"] for c in inspector.get_columns("messages")]
            if "human_agent_name" not in msg_columns:
                connection.execute(text(
                    "ALTER TABLE messages ADD COLUMN human_agent_name VARCHAR(100)"
                ))
            if "is_deleted_by_user" not in msg_columns:
                connection.execute(text(
                    "ALTER TABLE messages ADD COLUMN is_deleted_by_user BOOLEAN NOT NULL DEFAULT 0"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_messages_is_deleted_by_user ON messages(is_deleted_by_user)"
                ))
            if "deleted_by_customer_id" not in msg_columns:
                connection.execute(text(
                    "ALTER TABLE messages ADD COLUMN deleted_by_customer_id VARCHAR(64)"
                ))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_messages_deleted_by_customer_id ON messages(deleted_by_customer_id)"
                ))
            if "deleted_at" not in msg_columns:
                connection.execute(text(
                    "ALTER TABLE messages ADD COLUMN deleted_at DATETIME"
                ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_messages_timestamp ON messages(timestamp)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_messages_role_timestamp ON messages(role, timestamp)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_messages_conversation_deleted_timestamp "
                "ON messages(conversation_id, is_deleted_by_user, timestamp)"
            ))
        
        await conn.run_sync(_add_missing_columns)

    def _coerce_sql_date(value) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    # Bootstrap statistics snapshot once from existing conversation/message data.
    async with AsyncSessionLocal() as session:
        initialized = (
            await session.execute(select(StatisticsMeta).where(StatisticsMeta.key == "initialized"))
        ).scalar_one_or_none()
        if not initialized:
            existing_daily_rows = int(
                (await session.execute(select(func.count(StatisticsDaily.date)))).scalar() or 0
            )
            if existing_daily_rows == 0:
                daily_map: dict[date, dict[str, int]] = {}

                conv_rows = (
                    await session.execute(
                        select(func.date(Conversation.created_at).label("day"), func.count(Conversation.id))
                        .group_by(func.date(Conversation.created_at))
                    )
                ).all()
                for day_value, conversations_count in conv_rows:
                    day = _coerce_sql_date(day_value)
                    slot = daily_map.setdefault(
                        day,
                        {"conversations": 0, "messages": 0, "user_messages": 0, "assistant_messages": 0},
                    )
                    slot["conversations"] = int(conversations_count or 0)

                msg_rows = (
                    await session.execute(
                        select(
                            func.date(Message.timestamp).label("day"),
                            func.count(Message.id).label("messages"),
                            func.sum(case((Message.role == "user", 1), else_=0)).label("user_messages"),
                            func.sum(case((Message.role == "assistant", 1), else_=0)).label("assistant_messages"),
                        ).group_by(func.date(Message.timestamp))
                    )
                ).all()
                for day_value, messages_count, user_messages_count, assistant_messages_count in msg_rows:
                    day = _coerce_sql_date(day_value)
                    slot = daily_map.setdefault(
                        day,
                        {"conversations": 0, "messages": 0, "user_messages": 0, "assistant_messages": 0},
                    )
                    slot["messages"] = int(messages_count or 0)
                    slot["user_messages"] = int(user_messages_count or 0)
                    slot["assistant_messages"] = int(assistant_messages_count or 0)

                for day, bucket in daily_map.items():
                    session.add(
                        StatisticsDaily(
                            date=day,
                            conversations=bucket["conversations"],
                            messages=bucket["messages"],
                            user_messages=bucket["user_messages"],
                            assistant_messages=bucket["assistant_messages"],
                        )
                    )

            session.add(StatisticsMeta(key="initialized", value="1"))
            await session.commit()
    
    # Create default admin user if not exists (development convenience only)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        admin_user = result.scalar_one_or_none()
        
        if not admin_user and settings.DEBUG:
            admin_user = User(
                username="admin",
                password_hash=AuthService.hash_password("admin123"),
                display_name="管理员",
                email="admin@example.com",
                role="admin",
                is_active=True
            )
            session.add(admin_user)
            await session.commit()
            import logging
            logging.getLogger(__name__).warning("已创建默认管理员账号 admin（仅调试模式）。请尽快修改默认密码。")

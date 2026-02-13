"""Pytest Configuration and Fixtures"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, Conversation, Message, KnowledgeItem, Product, SystemSettings
from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def test_engine():
    """Create test database engine (in-memory SQLite)"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Create test database session"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(test_session: AsyncSession):
    """Create a test user for authentication tests"""
    user = await AuthService.create_user(
        test_session,
        username="test_agent",
        password="test_password",
        role="cs",
        display_name="Test Agent"
    )
    return user


@pytest_asyncio.fixture
async def test_admin_user(test_session: AsyncSession):
    """Create a test admin user"""
    user = await AuthService.create_user(
        test_session,
        username="test_admin",
        password="admin_password",
        role="admin",
        display_name="Test Admin"
    )
    return user

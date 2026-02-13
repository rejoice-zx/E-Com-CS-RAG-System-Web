# -*- coding: utf-8 -*-
"""Statistics API tests."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics import router as statistics_router
from app.database import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.utils.time import utcnow
from fastapi import FastAPI


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def statistics_client(test_session: AsyncSession):
    app = FastAPI()
    app.include_router(statistics_router)

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(test_session: AsyncSession) -> str:
    admin = await AuthService.create_user(
        db=test_session,
        username="stats_admin",
        password="stats_admin_pass",
        role="admin",
        display_name="Stats Admin",
        is_active=True,
    )
    return AuthService.create_access_token({"sub": str(admin.id), "username": admin.username})


@pytest.mark.asyncio
async def test_overview_total_conversations_is_cumulative(statistics_client: AsyncClient, test_session: AsyncSession, admin_token: str):
    conv = await ChatService.create_conversation(test_session, title="stats", customer_id="user_1")
    await ChatService.add_message(test_session, conv.id, role="user", content="hello")

    first = await statistics_client.get("/api/statistics/overview", headers=_auth_header(admin_token))
    assert first.status_code == 200
    first_total_conversations = first.json()["total_conversations"]
    first_total_messages = first.json()["total_messages"]

    today = utcnow().strftime("%Y-%m-%d")
    daily = await statistics_client.get(
        "/api/statistics/daily",
        headers=_auth_header(admin_token),
        params={"start_date": today, "end_date": today},
    )
    assert daily.status_code == 200
    assert daily.json()["days"] == 1

    assert await ChatService.delete_conversation(test_session, conv.id) is True

    second = await statistics_client.get("/api/statistics/overview", headers=_auth_header(admin_token))
    assert second.status_code == 200
    assert second.json()["total_conversations"] == first_total_conversations
    assert second.json()["total_messages"] == first_total_messages


@pytest.mark.asyncio
async def test_delete_statistics_data_modes(statistics_client: AsyncClient, test_session: AsyncSession, admin_token: str):
    conv = await ChatService.create_conversation(test_session, title="stats2", customer_id="user_2")
    await ChatService.add_message(test_session, conv.id, role="assistant", content="ok")

    today = utcnow().strftime("%Y-%m-%d")
    delete_range_resp = await statistics_client.post(
        "/api/statistics/data/delete",
        headers=_auth_header(admin_token),
        json={"mode": "date_range", "start_date": today, "end_date": today},
    )
    assert delete_range_resp.status_code == 200
    assert delete_range_resp.json()["success"] is True
    assert delete_range_resp.json()["deleted_days"] >= 1

    overview_after_range = await statistics_client.get("/api/statistics/overview", headers=_auth_header(admin_token))
    assert overview_after_range.status_code == 200
    assert overview_after_range.json()["total_conversations"] == 0
    assert overview_after_range.json()["total_messages"] == 0

    conv2 = await ChatService.create_conversation(test_session, title="stats3", customer_id="user_3")
    await ChatService.add_message(test_session, conv2.id, role="user", content="again")

    reset_all_resp = await statistics_client.post(
        "/api/statistics/data/delete",
        headers=_auth_header(admin_token),
        json={"mode": "reset_all"},
    )
    assert reset_all_resp.status_code == 200
    assert reset_all_resp.json()["success"] is True
    assert reset_all_resp.json()["deleted_conversations"] >= 1

# -*- coding: utf-8 -*-
"""Chat debug-rag authorization tests."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import router as chat_router
from app.database import get_db
from app.services.auth_service import AuthService


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def chat_client(test_session: AsyncSession):
    app = FastAPI()
    app.include_router(chat_router)

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_debug_rag_requires_staff_role(
    chat_client: AsyncClient,
    test_session: AsyncSession,
):
    guest_token = AuthService.create_access_token({"sub": "visitor_debug", "role": "guest"})

    customer = await AuthService.create_user(
        db=test_session,
        username="debug_customer",
        password="debug_customer_pass",
        role="customer",
        display_name="Debug Customer",
        is_active=True,
    )
    customer_token = AuthService.create_access_token(
        {"sub": str(customer.id), "username": customer.username}
    )

    cs = await AuthService.create_user(
        db=test_session,
        username="debug_cs",
        password="debug_cs_pass",
        role="cs",
        display_name="Debug CS",
        is_active=True,
    )
    cs_token = AuthService.create_access_token({"sub": str(cs.id), "username": cs.username})

    unauth = await chat_client.post("/api/chat/debug-rag", json={"query": "test"})
    assert unauth.status_code in (401, 403)

    guest_resp = await chat_client.post(
        "/api/chat/debug-rag",
        json={"query": "test"},
        headers=_auth_header(guest_token),
    )
    assert guest_resp.status_code == 401

    customer_resp = await chat_client.post(
        "/api/chat/debug-rag",
        json={"query": "test"},
        headers=_auth_header(customer_token),
    )
    assert customer_resp.status_code == 403

    cs_resp = await chat_client.post(
        "/api/chat/debug-rag",
        json={"query": "test"},
        headers=_auth_header(cs_token),
    )
    assert cs_resp.status_code == 200

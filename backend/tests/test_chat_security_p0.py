# -*- coding: utf-8 -*-
"""P0 chat security regression tests."""
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import router as chat_router
from app.database import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


@pytest_asyncio.fixture
async def chat_client(test_session: AsyncSession):
    """Build an API client with test DB dependency override."""
    app = FastAPI()
    app.include_router(chat_router)

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def guest_a_token() -> str:
    return AuthService.create_access_token({"sub": "visitor_a", "role": "guest"})


@pytest.fixture
def guest_b_token() -> str:
    return AuthService.create_access_token({"sub": "visitor_b", "role": "guest"})


@pytest_asyncio.fixture
async def admin_token(test_session: AsyncSession) -> str:
    admin_user = await AuthService.create_user(
        db=test_session,
        username="active_admin",
        password="admin_password",
        role="admin",
        display_name="Active Admin",
        is_active=True,
    )
    return AuthService.create_access_token(
        {"sub": str(admin_user.id), "username": admin_user.username}
    )


@pytest.mark.asyncio
async def test_conversation_list_requires_auth_token(chat_client: AsyncClient):
    response = await chat_client.get("/api/chat/conversations")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_guest_can_only_list_own_conversations(
    chat_client: AsyncClient,
    test_session: AsyncSession,
    guest_a_token: str,
):
    await ChatService.create_conversation(test_session, title="A", customer_id="visitor_a")
    await ChatService.create_conversation(test_session, title="B", customer_id="visitor_b")

    response = await chat_client.get(
        "/api/chat/conversations",
        headers=_auth_header(guest_a_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert all(item["customer_id"] == "visitor_a" for item in payload["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path_template,body,conversation_status",
    [
        ("GET", "/api/chat/conversations/{id}", None, "normal"),
        ("PUT", "/api/chat/conversations/{id}", {"title": "hacked"}, "normal"),
        ("DELETE", "/api/chat/conversations/{id}", None, "normal"),
        ("GET", "/api/chat/conversations/{id}/messages", None, "normal"),
        ("POST", "/api/chat/conversations/{id}/transfer-human", {"reason": "hack"}, "normal"),
        ("POST", "/api/chat/conversations/{id}/messages?stream=false", {"content": "hack"}, "human_handling"),
    ],
)
async def test_guest_cannot_access_other_guest_conversation(
    chat_client: AsyncClient,
    test_session: AsyncSession,
    guest_b_token: str,
    method: str,
    path_template: str,
    body: dict,
    conversation_status: str,
):
    conv = await ChatService.create_conversation(
        test_session,
        title="Owner A",
        customer_id="visitor_a",
    )
    await ChatService.update_conversation(test_session, conv.id, status=conversation_status)
    await ChatService.add_message(test_session, conv.id, role="user", content="seed")

    path = path_template.format(id=conv.id)
    response = await chat_client.request(
        method,
        path,
        json=body,
        headers=_auth_header(guest_b_token),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_all_conversations_requires_admin(
    chat_client: AsyncClient,
    test_session: AsyncSession,
    guest_a_token: str,
    admin_token: str,
):
    await ChatService.create_conversation(test_session, title="to delete", customer_id="visitor_a")

    unauth_response = await chat_client.delete("/api/chat/conversations")
    assert unauth_response.status_code in (401, 403)

    guest_response = await chat_client.delete(
        "/api/chat/conversations",
        headers=_auth_header(guest_a_token),
    )
    assert guest_response.status_code == 401

    admin_response = await chat_client.delete(
        "/api/chat/conversations",
        headers=_auth_header(admin_token),
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["deleted_count"] >= 1

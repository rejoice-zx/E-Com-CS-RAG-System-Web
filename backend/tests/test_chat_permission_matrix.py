# -*- coding: utf-8 -*-
"""Chat permission matrix regression tests."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import router as chat_router
from app.database import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


def _auth_header(token: str | None) -> dict[str, str]:
    if not token:
        return {}
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


@pytest_asyncio.fixture
async def matrix_context(test_session: AsyncSession):
    customer_a = await AuthService.create_user(
        db=test_session,
        username="matrix_customer_a",
        password="matrix_pass_a",
        role="customer",
        display_name="Matrix Customer A",
        is_active=True,
    )
    customer_b = await AuthService.create_user(
        db=test_session,
        username="matrix_customer_b",
        password="matrix_pass_b",
        role="customer",
        display_name="Matrix Customer B",
        is_active=True,
    )
    cs_user = await AuthService.create_user(
        db=test_session,
        username="matrix_cs",
        password="matrix_cs_pass",
        role="cs",
        display_name="Matrix CS",
        is_active=True,
    )
    admin_user = await AuthService.create_user(
        db=test_session,
        username="matrix_admin",
        password="matrix_admin_pass",
        role="admin",
        display_name="Matrix Admin",
        is_active=True,
    )

    tokens = {
        "unauth": None,
        "guest_owner": AuthService.create_access_token({"sub": "visitor_matrix_a", "role": "guest"}),
        "guest_other": AuthService.create_access_token({"sub": "visitor_matrix_b", "role": "guest"}),
        "customer_owner": AuthService.create_access_token(
            {"sub": str(customer_a.id), "username": customer_a.username}
        ),
        "customer_other": AuthService.create_access_token(
            {"sub": str(customer_b.id), "username": customer_b.username}
        ),
        "cs": AuthService.create_access_token({"sub": str(cs_user.id), "username": cs_user.username}),
        "admin": AuthService.create_access_token(
            {"sub": str(admin_user.id), "username": admin_user.username}
        ),
    }

    guest_conversation = await ChatService.create_conversation(
        test_session,
        title="guest owned",
        customer_id="visitor_matrix_a",
    )
    user_conversation = await ChatService.create_conversation(
        test_session,
        title="user owned",
        customer_id=f"user_{customer_a.id}",
    )
    await ChatService.add_message(test_session, guest_conversation.id, role="user", content="g")
    await ChatService.add_message(test_session, user_conversation.id, role="user", content="u")

    return {
        "tokens": tokens,
        "guest_conversation_id": guest_conversation.id,
        "user_conversation_id": user_conversation.id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_suffix", ["", "/messages"])
@pytest.mark.parametrize(
    "role_name,expected",
    [
        ("unauth", 401),
        ("guest_owner", 200),
        ("guest_other", 403),
        ("customer_owner", 403),
        ("customer_other", 403),
        ("cs", 200),
        ("admin", 200),
    ],
)
async def test_guest_conversation_permission_matrix(
    chat_client: AsyncClient,
    matrix_context: dict,
    endpoint_suffix: str,
    role_name: str,
    expected: int,
):
    token = matrix_context["tokens"][role_name]
    conv_id = matrix_context["guest_conversation_id"]

    response = await chat_client.get(
        f"/api/chat/conversations/{conv_id}{endpoint_suffix}",
        headers=_auth_header(token),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_suffix", ["", "/messages"])
@pytest.mark.parametrize(
    "role_name,expected",
    [
        ("unauth", 401),
        ("guest_owner", 403),
        ("guest_other", 403),
        ("customer_owner", 200),
        ("customer_other", 403),
        ("cs", 200),
        ("admin", 200),
    ],
)
async def test_user_conversation_permission_matrix(
    chat_client: AsyncClient,
    matrix_context: dict,
    endpoint_suffix: str,
    role_name: str,
    expected: int,
):
    token = matrix_context["tokens"][role_name]
    conv_id = matrix_context["user_conversation_id"]

    response = await chat_client.get(
        f"/api/chat/conversations/{conv_id}{endpoint_suffix}",
        headers=_auth_header(token),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_include_deleted_only_visible_to_staff(
    chat_client: AsyncClient,
    matrix_context: dict,
):
    conv_id = matrix_context["user_conversation_id"]
    owner_token = matrix_context["tokens"]["customer_owner"]
    cs_token = matrix_context["tokens"]["cs"]

    owner_list = await chat_client.get(
        f"/api/chat/conversations/{conv_id}/messages",
        headers=_auth_header(owner_token),
    )
    assert owner_list.status_code == 200
    message_id = owner_list.json()["items"][0]["id"]

    soft_delete = await chat_client.delete(
        f"/api/chat/conversations/{conv_id}/messages/{message_id}",
        headers=_auth_header(owner_token),
    )
    assert soft_delete.status_code == 204

    owner_with_include_deleted = await chat_client.get(
        f"/api/chat/conversations/{conv_id}/messages",
        params={"include_deleted": "true"},
        headers=_auth_header(owner_token),
    )
    assert owner_with_include_deleted.status_code == 200
    assert owner_with_include_deleted.json()["items"] == []

    cs_with_include_deleted = await chat_client.get(
        f"/api/chat/conversations/{conv_id}/messages",
        params={"include_deleted": "true"},
        headers=_auth_header(cs_token),
    )
    assert cs_with_include_deleted.status_code == 200
    assert len(cs_with_include_deleted.json()["items"]) == 1
    assert cs_with_include_deleted.json()["items"][0]["is_deleted_by_user"] is True

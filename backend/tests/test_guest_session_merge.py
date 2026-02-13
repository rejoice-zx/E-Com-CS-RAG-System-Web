# -*- coding: utf-8 -*-
"""Guest session migration regression tests."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.database import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_chat_client(test_session: AsyncSession):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(chat_router)

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_guest_create_conversation_persists_device_and_session_id(
    auth_chat_client: AsyncClient,
    test_session: AsyncSession,
):
    visitor_id = "visitor_merge_case"
    guest_token = AuthService.create_access_token({"sub": visitor_id, "role": "guest"})

    response = await auth_chat_client.post(
        "/api/chat/conversations",
        json={"title": "guest conv"},
        headers={
            **_auth_header(guest_token),
            "X-Device-ID": "device_merge_case",
        },
    )

    assert response.status_code == 201
    conversation_id = response.json()["id"]

    conversation = await ChatService.get_conversation(test_session, conversation_id)
    assert conversation is not None
    assert conversation.customer_id == visitor_id
    assert conversation.temp_device_id == "device_merge_case"
    assert conversation.temp_session_id == visitor_id


@pytest.mark.asyncio
async def test_login_migrates_guest_history_by_visitor_or_device_and_can_load_history(
    auth_chat_client: AsyncClient,
    test_session: AsyncSession,
):
    user = await AuthService.create_user(
        db=test_session,
        username="merge_login_user",
        password="merge_login_pass",
        role="customer",
        display_name="Merge Login User",
        is_active=True,
    )

    visitor_id = "visitor_login_merge"
    conv_by_visitor = await ChatService.create_conversation(
        test_session,
        title="by visitor",
        customer_id=visitor_id,
        temp_session_id=visitor_id,
        temp_device_id="device_shared",
    )
    conv_by_device = await ChatService.create_conversation(
        test_session,
        title="by device",
        customer_id="visitor_other_a",
        temp_device_id="device_shared",
    )
    conv_unrelated = await ChatService.create_conversation(
        test_session,
        title="unrelated",
        customer_id="visitor_other_b",
        temp_device_id="device_other",
    )

    login_response = await auth_chat_client.post(
        "/api/auth/login",
        json={
            "username": "merge_login_user",
            "password": "merge_login_pass",
            "visitor_id": visitor_id,
            "guest_device_id": "device_shared",
        },
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    token = payload["access_token"]
    user_customer_id = f"user_{payload['user']['id']}"

    conv1 = await ChatService.get_conversation(test_session, conv_by_visitor.id)
    conv2 = await ChatService.get_conversation(test_session, conv_by_device.id)
    conv3 = await ChatService.get_conversation(test_session, conv_unrelated.id)

    assert conv1.customer_id == user_customer_id
    assert conv2.customer_id == user_customer_id
    assert conv3.customer_id == "visitor_other_b"

    list_response = await auth_chat_client.get(
        "/api/chat/conversations",
        headers=_auth_header(token),
    )
    assert list_response.status_code == 200
    ids = {item["id"] for item in list_response.json()["items"]}
    assert conv_by_visitor.id in ids
    assert conv_by_device.id in ids
    assert conv_unrelated.id not in ids


@pytest.mark.asyncio
async def test_register_customer_migrates_by_conversation_id(
    auth_chat_client: AsyncClient,
    test_session: AsyncSession,
):
    conv_target = await ChatService.create_conversation(
        test_session,
        title="target",
        customer_id="visitor_target",
    )
    conv_untouched = await ChatService.create_conversation(
        test_session,
        title="untouched",
        customer_id="visitor_untouched",
    )

    register_response = await auth_chat_client.post(
        "/api/auth/register-customer",
        json={
            "username": "merge_register_user",
            "password": "merge_register_pass",
            "display_name": "Merge Register User",
            "guest_conversation_ids": [conv_target.id],
        },
    )

    assert register_response.status_code == 201
    payload = register_response.json()
    token = payload["access_token"]
    user_customer_id = f"user_{payload['user']['id']}"

    migrated = await ChatService.get_conversation(test_session, conv_target.id)
    untouched = await ChatService.get_conversation(test_session, conv_untouched.id)

    assert migrated.customer_id == user_customer_id
    assert untouched.customer_id == "visitor_untouched"

    list_response = await auth_chat_client.get(
        "/api/chat/conversations",
        headers=_auth_header(token),
    )
    assert list_response.status_code == 200
    ids = {item["id"] for item in list_response.json()["items"]}
    assert conv_target.id in ids
    assert conv_untouched.id not in ids

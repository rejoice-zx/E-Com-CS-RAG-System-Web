# -*- coding: utf-8 -*-
"""Chat message management tests."""
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


@pytest.mark.asyncio
async def test_message_soft_delete_and_admin_hard_delete(
    chat_client: AsyncClient,
    test_session: AsyncSession,
):
    customer = await AuthService.create_user(
        db=test_session,
        username="msg_customer",
        password="msg_password",
        role="customer",
        display_name="Msg Customer",
        is_active=True,
    )
    admin = await AuthService.create_user(
        db=test_session,
        username="msg_admin",
        password="admin_password",
        role="admin",
        display_name="Msg Admin",
        is_active=True,
    )

    customer_token = AuthService.create_access_token(
        {"sub": str(customer.id), "username": customer.username}
    )
    admin_token = AuthService.create_access_token(
        {"sub": str(admin.id), "username": admin.username}
    )

    conversation = await ChatService.create_conversation(
        test_session,
        title="消息删除测试",
        customer_id=f"user_{customer.id}",
    )
    msg1 = await ChatService.add_message(test_session, conversation.id, role="user", content="用户消息1")
    await ChatService.add_message(test_session, conversation.id, role="assistant", content="助手消息1")

    soft_delete = await chat_client.delete(
        f"/api/chat/conversations/{conversation.id}/messages/{msg1.id}",
        headers=_auth_header(customer_token),
    )
    assert soft_delete.status_code == 204

    customer_list = await chat_client.get(
        f"/api/chat/conversations/{conversation.id}/messages",
        headers=_auth_header(customer_token),
    )
    assert customer_list.status_code == 200
    customer_message_ids = {item["id"] for item in customer_list.json()["items"]}
    assert msg1.id not in customer_message_ids

    # --- 管理员不带 include_deleted 时，也应看不到软删除消息（默认行为） ---
    admin_list_default = await chat_client.get(
        f"/api/chat/conversations/{conversation.id}/messages",
        headers=_auth_header(admin_token),
    )
    assert admin_list_default.status_code == 200
    admin_default_ids = {item["id"] for item in admin_list_default.json()["items"]}
    assert msg1.id not in admin_default_ids, "默认不带 include_deleted 时管理员也看不到软删除消息"

    # --- 管理员带 include_deleted=true 时，应能看到软删除消息 ---
    admin_list = await chat_client.get(
        f"/api/chat/conversations/{conversation.id}/messages",
        params={"include_deleted": True},
        headers=_auth_header(admin_token),
    )
    assert admin_list.status_code == 200
    admin_items = admin_list.json()["items"]
    admin_message_ids = {item["id"] for item in admin_items}
    assert msg1.id in admin_message_ids

    # --- 管理员硬删除后，即使 include_deleted=true 也看不到 ---
    hard_delete = await chat_client.delete(
        f"/api/chat/conversations/{conversation.id}/messages/{msg1.id}",
        params={"hard": True},
        headers=_auth_header(admin_token),
    )
    assert hard_delete.status_code == 204

    admin_list_after = await chat_client.get(
        f"/api/chat/conversations/{conversation.id}/messages",
        params={"include_deleted": True},
        headers=_auth_header(admin_token),
    )
    assert admin_list_after.status_code == 200
    admin_ids_after = {item["id"] for item in admin_list_after.json()["items"]}
    assert msg1.id not in admin_ids_after

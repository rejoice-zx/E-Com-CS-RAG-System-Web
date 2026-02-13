# -*- coding: utf-8 -*-
"""Chat message send APIs with optional SSE streaming."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.dependencies import (
    get_authorized_conversation,
    get_configured_llm_service,
    get_rag_service,
)
from app.database import get_db
from app.models.conversation import Conversation
from app.models.knowledge import KnowledgeItem
from app.schemas.chat import MessageResponse, SendMessageRequest, SendMessageResponse
from app.services.chat_service import ChatService
from app.services.knowledge_service import KnowledgeService
from app.services.llm_service import LLMService, LLMServiceError
from app.services.rag_service import RAGSearchResult, RAGService
from app.services.statistics_service import StatisticsService
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


LOW_CONFIDENCE_THRESHOLD = 0.35
DEFAULT_REPLY_WHEN_LLM_DISABLED = (
    "AI service is not configured. Please configure LLM settings and try again."
)
LOW_CONFIDENCE_HINT = (
    "\n\nHint: confidence is low. You can transfer this conversation to a human agent for better support."
)

_KNOWLEDGE_CACHE_TTL_SECONDS = 30.0
_knowledge_cache: Dict[str, Any] = {
    "signature": None,
    "expires_at": 0.0,
    "items": [],
}


def _history_limits() -> Tuple[int, int]:
    from app.core.config import Config

    cfg = Config()
    max_messages = int(cfg.get("history_max_messages", 12))
    max_chars = int(cfg.get("history_max_chars", 6000))
    return max_messages, max_chars


def _build_final_prompt_text(messages: List[Dict[str, str]]) -> str:
    prompt_parts: List[str] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        prompt_parts.append(f"[{role}]\n{content}")
    return "\n\n".join(prompt_parts)


def _ensure_rag_result(
    rag_result: Optional[RAGSearchResult],
    user_content: str,
    final_prompt_text: str,
) -> RAGSearchResult:
    if rag_result is None:
        return RAGSearchResult(
            query=user_content,
            rewritten_query=user_content,
            final_prompt=final_prompt_text,
        )
    rag_result.final_prompt = final_prompt_text
    return rag_result


async def _ensure_embedding_config_synced(db: AsyncSession) -> None:
    vector_service = VectorService()
    await vector_service.sync_config_from_db(db)


def _to_rag_knowledge_items(items_db: List[KnowledgeItem]) -> List[Dict[str, Any]]:
    return [
        {
            "id": item.id,
            "question": item.question,
            "answer": item.answer,
            "keywords": item.keywords or [],
            "category": item.category or "general",
        }
        for item in items_db
    ]


async def _get_cached_knowledge_items(db: AsyncSession) -> List[Dict[str, Any]]:
    now_monotonic = time.monotonic()

    signature_result = await db.execute(
        select(func.max(KnowledgeItem.updated_at), func.count(KnowledgeItem.id))
    )
    latest_updated_at, total = signature_result.one()
    signature = (
        latest_updated_at.isoformat() if latest_updated_at else "",
        int(total or 0),
    )

    if (
        _knowledge_cache.get("signature") == signature
        and _knowledge_cache.get("expires_at", 0.0) > now_monotonic
    ):
        return list(_knowledge_cache.get("items", []))

    knowledge_items_db = await KnowledgeService.get_all_knowledge_items(db)
    knowledge_items = _to_rag_knowledge_items(knowledge_items_db) if knowledge_items_db else []

    _knowledge_cache["signature"] = signature
    _knowledge_cache["items"] = knowledge_items
    _knowledge_cache["expires_at"] = now_monotonic + _KNOWLEDGE_CACHE_TTL_SECONDS
    return list(knowledge_items)


async def _prepare_chat_messages(
    db: AsyncSession,
    conversation_id: str,
    user_content: str,
    rag_service: RAGService,
) -> Tuple[List[Dict[str, str]], RAGSearchResult, Optional[float]]:
    await _ensure_embedding_config_synced(db)

    rag_result: Optional[RAGSearchResult] = None
    context_text: Optional[str] = None
    confidence: Optional[float] = None

    try:
        knowledge_items = await _get_cached_knowledge_items(db)
        if knowledge_items:
            rag_result = await rag_service.search(user_content, knowledge_items)
            context_text = rag_result.context_text
            confidence = rag_result.confidence
    except Exception as exc:
        logger.warning("RAG search failed, fallback to plain LLM: %s", exc)

    history_messages = await ChatService.get_all_messages(db, conversation_id)
    max_messages, max_chars = _history_limits()
    history = ChatService.messages_to_history(
        history_messages[:-1],
        max_messages=max_messages,
        max_chars=max_chars,
    )

    messages = rag_service.build_messages(user_content, context_text, history)
    final_prompt_text = _build_final_prompt_text(messages)
    rag_result = _ensure_rag_result(rag_result, user_content, final_prompt_text)
    return messages, rag_result, confidence


async def generate_sse_response(
    db: AsyncSession,
    conversation_id: str,
    user_content: str,
    rag_service: RAGService,
    llm_service: LLMService,
):
    """Generate SSE chunks for one chat request."""
    from app.services.performance_service import get_performance_service

    perf = get_performance_service()
    chat_start = time.perf_counter()
    chat_success = True

    try:
        user_message = await ChatService.add_message(
            db,
            conversation_id,
            role="user",
            content=user_content,
        )
        StatisticsService.record_question(user_content)

        if not user_message:
            chat_success = False
            yield f"data: {json.dumps({'type': 'error', 'message': 'failed to save user message'}, ensure_ascii=False)}\n\n"
            return

        yield f"data: {json.dumps({'type': 'start', 'user_message_id': user_message.id}, ensure_ascii=False)}\n\n"

        messages, rag_result, confidence = await _prepare_chat_messages(
            db,
            conversation_id,
            user_content,
            rag_service,
        )

        yield f"data: {json.dumps({'type': 'rag_trace', 'trace': rag_result.to_dict()}, ensure_ascii=False)}\n\n"

        if not llm_service.is_configured:
            full_content = DEFAULT_REPLY_WHEN_LLM_DISABLED
            yield f"data: {json.dumps({'type': 'content', 'content': full_content}, ensure_ascii=False)}\n\n"
        else:
            full_content = ""
            try:
                async for chunk in llm_service.chat_stream(messages):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
            except LLMServiceError as exc:
                chat_success = False
                full_content = f"AI service error: {exc.message}"
                yield f"data: {json.dumps({'type': 'error', 'message': full_content}, ensure_ascii=False)}\n\n"

        assistant_message = await ChatService.add_message(
            db,
            conversation_id,
            role="assistant",
            content=full_content,
            confidence=confidence,
            rag_trace=rag_result.to_dict(),
        )

        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            yield f"data: {json.dumps({'type': 'content', 'content': LOW_CONFIDENCE_HINT}, ensure_ascii=False)}\n\n"
            full_content += LOW_CONFIDENCE_HINT
            assistant_message.content = full_content
            await db.commit()
            yield f"data: {json.dumps({'type': 'low_confidence', 'confidence': confidence, 'suggest_human': True}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'end', 'message_id': assistant_message.id, 'confidence': confidence}, ensure_ascii=False)}\n\n"

    except Exception as exc:
        chat_success = False
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
    finally:
        chat_duration = time.perf_counter() - chat_start
        perf.record("chat_api", chat_duration, chat_success)


def register_streaming_routes(router: APIRouter):
    """Register message send endpoint."""

    @router.post("/conversations/{conversation_id}/messages")
    async def send_message(
        request: SendMessageRequest,
        conversation: Conversation = Depends(get_authorized_conversation),
        stream: bool = Query(True, description="Enable SSE stream response"),
        db: AsyncSession = Depends(get_db),
        rag_service: RAGService = Depends(get_rag_service),
        llm_service: LLMService = Depends(get_configured_llm_service),
    ):
        allowed_statuses = ["normal", "human_handling"]
        if conversation.status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"conversation status does not allow sending messages: {conversation.status}",
            )

        if conversation.status == "human_handling":
            user_message = await ChatService.add_message(
                db,
                conversation.id,
                role="user",
                content=request.content,
            )
            StatisticsService.record_question(request.content)

            if not user_message:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="failed to save user message",
                )

            # 实时推送消息到 B 端客服 WebSocket
            from app.services.ws_manager import ws_manager
            delivered_to_agent_ws = ws_manager.has_conversation_connections(conversation.id)
            if delivered_to_agent_ws:
                await ws_manager.send_to_conversation_agents(conversation.id, {
                    "type": "message",
                    "id": user_message.id,
                    "conversation_id": user_message.conversation_id,
                    "role": user_message.role,
                    "content": user_message.content,
                    "timestamp": user_message.timestamp.isoformat(),
                })

            # 回推给客户自身的 WebSocket（多标签页同步 + 服务端确认真实 ID）
            if conversation.customer_id:
                await ws_manager.send_to_customer(conversation.customer_id, {
                    "type": "message",
                    "id": user_message.id,
                    "conversation_id": user_message.conversation_id,
                    "role": user_message.role,
                    "content": user_message.content,
                    "timestamp": user_message.timestamp.isoformat(),
                })

            # 通知所有客服全局通道：该对话有新客户消息
            await ws_manager.broadcast_to_all_agents({
                "type": "new_message",
                "conversation_id": user_message.conversation_id,
                "message": {
                    "id": user_message.id,
                    "role": user_message.role,
                    "content": user_message.content,
                    "timestamp": user_message.timestamp.isoformat(),
                },
            })

            return {
                "user_message": {
                    "id": user_message.id,
                    "conversation_id": user_message.conversation_id,
                    "role": user_message.role,
                    "content": user_message.content,
                    "timestamp": user_message.timestamp.isoformat(),
                },
                "assistant_message": None,
                "status": "human_handling",
                "message": "message delivered to human agent",
                "delivered_to_agent_ws": delivered_to_agent_ws,
            }

        if stream:
            return StreamingResponse(
                generate_sse_response(
                    db,
                    conversation.id,
                    request.content,
                    rag_service,
                    llm_service,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        user_message = await ChatService.add_message(
            db,
            conversation.id,
            role="user",
            content=request.content,
        )
        StatisticsService.record_question(request.content)

        if not user_message:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to save user message",
            )

        messages, rag_result, confidence = await _prepare_chat_messages(
            db,
            conversation.id,
            request.content,
            rag_service,
        )

        if llm_service.is_configured:
            try:
                response = await llm_service.chat(messages)
                reply_content = response.content
            except LLMServiceError as exc:
                reply_content = f"AI service error: {exc.message}"
        else:
            reply_content = DEFAULT_REPLY_WHEN_LLM_DISABLED

        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            reply_content += LOW_CONFIDENCE_HINT

        assistant_message = await ChatService.add_message(
            db,
            conversation.id,
            role="assistant",
            content=reply_content,
            confidence=confidence,
            rag_trace=rag_result.to_dict(),
        )

        return SendMessageResponse(
            user_message=MessageResponse(
                id=user_message.id,
                conversation_id=user_message.conversation_id,
                role=user_message.role,
                content=user_message.content,
                confidence=user_message.confidence,
                rag_trace=user_message.rag_trace,
                is_deleted_by_user=False,
                deleted_by_customer_id=None,
                deleted_at=None,
                timestamp=user_message.timestamp,
            ),
            assistant_message=MessageResponse(
                id=assistant_message.id,
                conversation_id=assistant_message.conversation_id,
                role=assistant_message.role,
                content=assistant_message.content,
                confidence=assistant_message.confidence,
                rag_trace=assistant_message.rag_trace,
                is_deleted_by_user=False,
                deleted_by_customer_id=None,
                deleted_at=None,
                timestamp=assistant_message.timestamp,
            ),
        )

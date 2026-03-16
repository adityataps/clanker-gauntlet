"""
WebSocket endpoint — streams session events to connected clients.

Each session has a Redis Stream key: session:{session_id}:events
The EventRunner publishes STAT_UPDATE events there; all other event types are
also broadcast so the UI can update standings, scores, and agent decisions in
real time.

Connection:
    WS /ws/sessions/{session_id}
    Authorization: Bearer <token> passed as a query param (?token=...) since
    the browser WebSocket API does not support custom headers.

Protocol (server → client):
    Each message is a JSON object:
    { "type": "<event_type>", "seq": <int>, "payload": {...} }

    Special message types:
    { "type": "connected", "session_id": "..." }   — sent on successful auth
    { "type": "error", "detail": "..." }            — sent before close on error

The broadcaster reads the Redis Stream starting from the last-seen ID per
connection (starts from "$" i.e. new events only, not history). For clients
that need replay, the EventRunner's processed_events table is the source —
WebSocket is for live delivery only.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from backend.auth.jwt import decode_access_token
from backend.config import settings
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# How often to poll the Redis stream when there are no new messages (seconds)
_POLL_INTERVAL = 0.5
# Max messages to read per poll
_BLOCK_MS = 500


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    """
    Stream live session events to a connected client.

    Auth: pass JWT as ?token=<jwt> query param.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("No sub in token")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Verify the user is a member of this session
    from sqlalchemy import select

    from backend.db.models import SessionMembership

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionMembership).where(
                SessionMembership.session_id == session_id,
                SessionMembership.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            await websocket.close(code=4003, reason="Not a member of this session")
            return

    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "connected", "session_id": session_id}))

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    stream_key = f"session:{session_id}:events"
    last_id = "$"  # only new events from this point forward

    try:
        while True:
            try:
                results = await redis.xread({stream_key: last_id}, block=_BLOCK_MS, count=50)
            except Exception as exc:
                logger.warning("Redis read error for session %s: %s", session_id, exc)
                await asyncio.sleep(_POLL_INTERVAL)
                continue

            if results:
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": fields.get("event_type", "unknown"),
                                        "seq": fields.get("seq"),
                                        "payload": json.loads(fields.get("payload", "{}")),
                                    }
                                )
                            )
                        except Exception:
                            logger.exception("Failed to serialize event for session %s", session_id)

    except WebSocketDisconnect:
        logger.info("Client disconnected from session %s", session_id)
    finally:
        await redis.aclose()

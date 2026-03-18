"""
WebSocket endpoint — streams session events to connected clients.

Two Redis Stream keys per session:
    session:{id}:broadcast      — all events; every connected client reads this
    session:{id}:team:{team_id} — team-specific reaction window notifications

Connection:
    WS /ws/sessions/{session_id}
    Authorization: Bearer <token> passed as a query param (?token=...) since
    the browser WebSocket API does not support custom headers.

Protocol (server → client):
    Each message is a JSON object:
    { "type": "<event_type>", "seq": <int>, "payload": {...} }

    Special message types:
    { "type": "connected", "session_id": "...", "team_id": "<uuid|null>" }
    { "type": "error", "detail": "..." }

The broadcaster reads both streams starting from "$" (new events only).
For replay, query the processed_events table via REST — WS is live-only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import select

from backend.auth.jwt import decode_access_token
from backend.config import settings
from backend.db.models import SessionMembership
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

_BLOCK_MS = 500
_POLL_INTERVAL = 0.5


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    """
    Stream live session events to a connected client.

    Auth: pass JWT as ?token=<jwt> query param.
    Reads from broadcast stream and, if the user has a team, their team stream.
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

    # Verify membership and resolve team_id (None for observers)
    team_id: uuid.UUID | None = None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionMembership).where(
                SessionMembership.session_id == session_id,
                SessionMembership.user_id == user_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            await websocket.close(code=4003, reason="Not a member of this session")
            return
        team_id = membership.team_id  # None for observers

    await websocket.accept()
    await websocket.send_text(
        json.dumps(
            {
                "type": "connected",
                "session_id": session_id,
                "team_id": str(team_id) if team_id else None,
            }
        )
    )

    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    broadcast_key = f"session:{session_id}:broadcast"
    team_key = f"session:{session_id}:team:{team_id}" if team_id else None

    # Track last-seen IDs separately per stream
    last_broadcast = "$"
    last_team = "$"

    try:
        while True:
            streams: dict[str, str] = {broadcast_key: last_broadcast}
            if team_key:
                streams[team_key] = last_team

            try:
                results = await redis.xread(streams, block=_BLOCK_MS, count=50)
            except Exception as exc:
                logger.warning("Redis read error for session %s: %s", session_id, exc)
                await asyncio.sleep(_POLL_INTERVAL)
                continue

            if results:
                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        # Advance the correct cursor
                        if stream_name == broadcast_key:
                            last_broadcast = msg_id
                        else:
                            last_team = msg_id

                        try:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": fields.get("event_type", "unknown"),
                                        "seq": fields.get("seq"),
                                        "payload": json.loads(fields.get("payload", "{}")),
                                        # informational=true means all teams see it but only
                                        # the recipient is expected to act
                                        "informational": fields.get("informational") == "true",
                                    }
                                )
                            )
                        except Exception:
                            logger.exception("Failed to serialize event for session %s", session_id)

    except WebSocketDisconnect:
        logger.info("Client disconnected from session %s", session_id)
    finally:
        await redis.aclose()

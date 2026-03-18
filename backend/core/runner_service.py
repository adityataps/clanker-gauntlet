"""
EventRunnerService — application-level singleton that manages all session runners.

One asyncio.Task is spawned per active session. Tasks share the same event loop
and run concurrently. Each task has its own cursor, WorldState, and team set —
they are fully isolated from one another.

Lifecycle:
    start(session_id, teams)  →  spawn a Task for the session
    pause(session_id)         →  cancel the Task (cursor already persisted per-event)
    resume(session_id, teams) →  same as start; runner reloads cursor from DB

The service is instantiated once at FastAPI startup and injected as a dependency.

Usage:
    # In FastAPI lifespan:
    runner_service = EventRunnerService(AsyncSessionLocal, redis_client)

    # Start a session (e.g. after session status transitions to IN_PROGRESS):
    await runner_service.start(session_id, teams)

    # Pause (e.g. user hits pause button):
    await runner_service.pause(session_id)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.event_runner import EventRunner
from backend.core.world_state import WorldState
from backend.db.models import Session, SessionStatus, Snapshot
from backend.teams.protocol import BaseTeam

logger = logging.getLogger(__name__)


class EventRunnerService:
    """
    Manages all active session runner tasks.

    Args:
        db_session_factory: Callable that returns an async context manager
                            yielding an AsyncSession (e.g. AsyncSessionLocal).
        redis:              Optional Redis client passed through to each runner.
    """

    def __init__(
        self,
        db_session_factory: Callable,
        redis: Any | None = None,
    ) -> None:
        self._db_factory = db_session_factory
        self._redis = redis
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(
        self,
        session_id: uuid.UUID,
        teams: dict[uuid.UUID, BaseTeam],
    ) -> None:
        """
        Start running a session. No-op if the session is already running.
        The runner reads script_speed and current_seq from the DB row.
        """
        if self.is_running(session_id):
            logger.info("Session %s is already running — ignoring start()", session_id)
            return

        task = asyncio.create_task(
            self._run_session(session_id, teams),
            name=f"runner:{session_id}",
        )
        # Auto-remove from registry when the task finishes (normally or via exception)
        task.add_done_callback(lambda _: self._tasks.pop(session_id, None))
        self._tasks[session_id] = task
        logger.info("Session %s started", session_id)

    async def pause(self, session_id: uuid.UUID) -> None:
        """
        Pause a running session by cancelling its task.
        The cursor is already persisted after each event, so resuming
        later via start() picks up exactly where it left off.
        """
        task = self._tasks.pop(session_id, None)
        if task is None or task.done():
            logger.info("Session %s is not running — nothing to pause", session_id)
            return

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        logger.info("Session %s paused", session_id)

    def is_running(self, session_id: uuid.UUID) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    def active_sessions(self) -> list[uuid.UUID]:
        return [sid for sid, task in self._tasks.items() if not task.done()]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_session(
        self,
        session_id: uuid.UUID,
        teams: dict[uuid.UUID, BaseTeam],
    ) -> None:
        """
        Load session config + world state, build EventRunner, and run it.
        Each session gets its own DB connection for isolation.
        """
        async with self._db_factory() as db:
            session_row = await db.get(Session, session_id)
            if session_row is None:
                logger.error("Session %s not found in DB — aborting", session_id)
                return

            if session_row.status == SessionStatus.COMPLETED:
                logger.info("Session %s is already COMPLETED — nothing to run", session_id)
                return

            world_state = await self._load_world_state(db, session_row, teams)

            runner = EventRunner(
                session_id=session_id,
                script_id=session_row.script_id,
                db=db,
                teams=teams,
                world_state=world_state,
                script_speed=session_row.script_speed,
                redis=self._redis,
            )
            runner._waiver_mode = session_row.waiver_mode
            runner._priority_reset = session_row.priority_reset
            runner._compression_factor = session_row.compression_factor
            runner._wall_start_time = session_row.wall_start_time
            runner._reaction_timeouts = (session_row.session_config or {}).get(
                "reaction_timeouts", {}
            )

            try:
                await runner.run()
            except asyncio.CancelledError:
                logger.info("Session %s runner cancelled (paused)", session_id)
                raise  # let the task framework see it
            except Exception:
                logger.exception("Session %s runner crashed", session_id)

    async def _load_world_state(
        self,
        db: AsyncSession,
        session_row: Session,
        teams: dict[uuid.UUID, BaseTeam],
    ) -> WorldState:
        """
        Load the most recent snapshot for this session, or create a fresh
        WorldState if none exists yet.
        """
        result = await db.execute(
            select(Snapshot)
            .where(Snapshot.session_id == session_row.id)
            .order_by(Snapshot.seq.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()

        if snapshot is not None:
            logger.info(
                "Session %s: resuming from snapshot at seq=%d week=%d",
                session_row.id,
                snapshot.seq,
                snapshot.period_number,
            )
            return WorldState.from_snapshot(snapshot.world_state)

        logger.info("Session %s: no snapshot found — creating fresh WorldState", session_row.id)
        return WorldState.create(
            session_id=session_row.id,
            team_ids=list(teams.keys()),
            initial_faab=100,
        )

"""
Taskiq worker — long-running background tasks.

Start the worker (separate process from the API):
    taskiq worker backend.worker:broker

The broker is also imported by:
  - backend/main.py   → broker.startup() / broker.shutdown() in lifespan
  - backend/api/admin.py → compile_script_task.kiq(...)
"""

import logging
import uuid
from datetime import UTC, datetime

from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Broker ────────────────────────────────────────────────────────────────────

result_backend = RedisAsyncResultBackend(settings.redis_url)
broker = ListQueueBroker(settings.redis_url).with_result_backend(result_backend)


# ── Tasks ─────────────────────────────────────────────────────────────────────


@broker.task
async def compile_script_task(
    script_id: str,
    sport: str,
    season: int,
    season_type: str,
) -> dict:
    """
    Compile a season script into the DB.

    Expects a SeasonScript record with status=PENDING to already exist
    (created by the admin endpoint before enqueueing this task).
    Updates the record to COMPILED or FAILED on completion.

    Returns a summary dict that Taskiq stores in the result backend.
    """
    from sqlalchemy import select

    from backend.data.compiler import ScriptCompiler
    from backend.db.models import ScriptStatus, SeasonScript
    from backend.db.session import AsyncSessionLocal

    script_uuid = uuid.UUID(script_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SeasonScript).where(SeasonScript.id == script_uuid))
        script = result.scalar_one_or_none()

        if script is None:
            logger.error("compile_script_task: SeasonScript %s not found", script_id)
            return {"error": "Script record not found"}

        compiler = ScriptCompiler(db)
        try:
            total = await compiler._compile_nfl(script)
            script.status = ScriptStatus.COMPILED
            script.total_events = total
            script.compiled_at = datetime.now(UTC)
            await db.commit()
            logger.info(
                "compile_script_task: compiled %s %s %s — %d events",
                sport,
                season,
                season_type,
                total,
            )
            return {"script_id": script_id, "total_events": total}

        except Exception:
            logger.exception("compile_script_task: failed for %s %s %s", sport, season, season_type)
            script.status = ScriptStatus.FAILED
            await db.commit()
            raise

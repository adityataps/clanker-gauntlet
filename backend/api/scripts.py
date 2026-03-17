"""
Season script endpoints.

Scripts are compiled once (via ScriptCompiler) and shared across all sessions
that backtest the same season. These endpoints expose available scripts for
the session-creation UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import ScriptStatus, SeasonEvent, SeasonScript
from backend.db.session import get_db

router = APIRouter(prefix="/scripts", tags=["scripts"])


class ScriptResponse(BaseModel):
    id: uuid.UUID
    sport: str
    season: int
    season_type: str
    total_events: int
    total_sim_hours: float
    """Total simulated hours spanned by this script (MAX sim_offset_hours).
    Used by the session-creation UI to compute compression_factor from a
    user-facing season duration in hours:
        compression_factor = ceil(total_sim_hours / desired_wall_hours)
    """
    status: str
    compiled_at: datetime | None


async def _sim_hours(script_id: uuid.UUID, db: AsyncSession) -> float:
    """Return MAX(sim_offset_hours) for the given script, or 0.0 if no events."""
    result = await db.scalar(
        select(func.max(SeasonEvent.sim_offset_hours)).where(SeasonEvent.script_id == script_id)
    )
    return float(result or 0.0)


@router.get("", response_model=list[ScriptResponse])
async def list_scripts(
    _: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """List all successfully compiled season scripts available for session creation."""
    result = await db.execute(
        select(SeasonScript)
        .where(SeasonScript.status == ScriptStatus.COMPILED)
        .order_by(SeasonScript.season.desc(), SeasonScript.sport)
    )
    scripts = result.scalars().all()
    # Batch the MAX queries — one per script; typically a single row anyway.
    rows = []
    for s in scripts:
        rows.append(
            ScriptResponse(
                id=s.id,
                sport=s.sport,
                season=s.season,
                season_type=s.season_type,
                total_events=s.total_events,
                total_sim_hours=await _sim_hours(s.id, db),
                status=s.status,
                compiled_at=s.compiled_at,
            )
        )
    return rows


@router.get("/{script_id}", response_model=ScriptResponse)
async def get_script(
    script_id: uuid.UUID,
    _: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    script = await db.get(SeasonScript, script_id)
    if script is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Script not found")
    return ScriptResponse(
        id=script.id,
        sport=script.sport,
        season=script.season,
        season_type=script.season_type,
        total_events=script.total_events,
        total_sim_hours=await _sim_hours(script.id, db),
        status=script.status,
        compiled_at=script.compiled_at,
    )

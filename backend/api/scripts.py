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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import ScriptStatus, SeasonScript
from backend.db.session import get_db

router = APIRouter(prefix="/scripts", tags=["scripts"])


class ScriptResponse(BaseModel):
    id: uuid.UUID
    sport: str
    season: int
    season_type: str
    total_events: int
    status: str
    compiled_at: datetime | None


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
    return [
        ScriptResponse(
            id=s.id,
            sport=s.sport,
            season=s.season,
            season_type=s.season_type,
            total_events=s.total_events,
            status=s.status,
            compiled_at=s.compiled_at,
        )
        for s in scripts
    ]


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
        status=script.status,
        compiled_at=script.compiled_at,
    )

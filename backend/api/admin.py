"""Admin API — server-admin only endpoints."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.config import settings
from backend.db.models import (
    League,
    LeagueMembership,
    ScriptStatus,
    SeasonScript,
    SeasonType,
    Session,
    User,
)
from backend.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth ──────────────────────────────────────────────────────────────────────


async def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not settings.admin_email_set:
        raise HTTPException(
            status_code=503, detail="Admin access not configured (set ADMIN_EMAILS)"
        )
    if current_user.email.lower() not in settings.admin_email_set:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Response models ───────────────────────────────────────────────────────────


class AdminStatsResponse(BaseModel):
    user_count: int
    league_count: int
    session_count: int
    script_count: int


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminLeagueResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    member_count: int
    session_count: int
    created_at: datetime


class AdminScriptResponse(BaseModel):
    id: uuid.UUID
    sport: str
    season: int
    season_type: str
    status: str
    total_events: int
    compiled_at: datetime | None

    model_config = {"from_attributes": True}


class CompileRequest(BaseModel):
    sport: str = "nfl"
    season: int = 2025
    season_type: str = "regular"
    force: bool = False


class CompileResponse(BaseModel):
    script_id: uuid.UUID
    status: str
    message: str


# ── Compile background task ───────────────────────────────────────────────────


async def _run_compile(script_id: uuid.UUID, sport: str, season: int, season_type: str) -> None:
    """Background coroutine: compiles into the already-created pending SeasonScript."""
    from backend.data.compiler import ScriptCompiler
    from backend.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SeasonScript).where(SeasonScript.id == script_id))
        script = result.scalar_one_or_none()
        if script is None:
            return
        compiler = ScriptCompiler(db)
        try:
            total = await compiler._compile_nfl(script)
            script.status = ScriptStatus.COMPILED
            script.total_events = total
            script.compiled_at = datetime.now(UTC)
            await db.commit()
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Admin compile failed for %s %s %s", sport, season, season_type
            )
            script.status = ScriptStatus.FAILED
            await db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    league_count = (await db.execute(select(func.count()).select_from(League))).scalar_one()
    session_count = (await db.execute(select(func.count()).select_from(Session))).scalar_one()
    script_count = (await db.execute(select(func.count()).select_from(SeasonScript))).scalar_one()
    return AdminStatsResponse(
        user_count=user_count,
        league_count=league_count,
        session_count=session_count,
        script_count=script_count,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.get("/leagues", response_model=list[AdminLeagueResponse])
async def list_leagues(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> list[AdminLeagueResponse]:
    result = await db.execute(select(League).order_by(League.created_at.desc()))
    leagues = result.scalars().all()
    out: list[AdminLeagueResponse] = []
    for league in leagues:
        member_count = (
            await db.execute(select(func.count()).where(LeagueMembership.league_id == league.id))
        ).scalar_one()
        session_count = (
            await db.execute(select(func.count()).where(Session.league_id == league.id))
        ).scalar_one()
        out.append(
            AdminLeagueResponse(
                id=league.id,
                name=league.name,
                created_by=league.created_by,
                member_count=member_count,
                session_count=session_count,
                created_at=league.created_at,
            )
        )
    return out


@router.get("/scripts", response_model=list[AdminScriptResponse])
async def list_scripts(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> list[AdminScriptResponse]:
    result = await db.execute(
        select(SeasonScript).order_by(SeasonScript.compiled_at.desc().nullslast())
    )
    return list(result.scalars().all())


@router.post("/scripts/compile", response_model=CompileResponse, status_code=202)
async def compile_script(
    body: CompileRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> CompileResponse:
    # Check for an existing script
    existing_result = await db.execute(
        select(SeasonScript).where(
            SeasonScript.sport == body.sport,
            SeasonScript.season == body.season,
            SeasonScript.season_type == SeasonType(body.season_type),
        )
    )
    script = existing_result.scalar_one_or_none()

    if script and script.status == ScriptStatus.PENDING:
        return CompileResponse(
            script_id=script.id,
            status="pending",
            message="Compilation already in progress.",
        )

    if script and script.status == ScriptStatus.COMPILED and not body.force:
        return CompileResponse(
            script_id=script.id,
            status="compiled",
            message=f"Already compiled ({script.total_events} events). Set force=true to recompile.",
        )

    # Delete existing if force-recompiling
    if script and body.force:
        await db.delete(script)
        await db.commit()

    # Create pending record; background task will compile into it
    new_script = SeasonScript(
        sport=body.sport,
        season=body.season,
        season_type=SeasonType(body.season_type),
        status=ScriptStatus.PENDING,
    )
    db.add(new_script)
    await db.commit()
    await db.refresh(new_script)

    asyncio.create_task(_run_compile(new_script.id, body.sport, body.season, body.season_type))

    return CompileResponse(
        script_id=new_script.id,
        status="pending",
        message=f"Compilation started for {body.sport} {body.season} {body.season_type}.",
    )

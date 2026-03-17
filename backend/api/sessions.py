import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_runner_service
from backend.auth.dependencies import get_current_user
from backend.core.runner_service import EventRunnerService
from backend.core.team_factory import load_teams_for_session
from backend.db.models import (
    LeagueMembership,
    LeagueMembershipStatus,
    MembershipRole,
    SeasonEvent,
    SeasonScript,
    Session,
    SessionMembership,
    SessionStatus,
    Team,
    TeamType,
)
from backend.db.session import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])

_BOT_CONFIG = {
    "archetype": "analytician",
    "reasoning_depth": "standard",
    "provider": "anthropic",
}


class JoinSessionResponse(BaseModel):
    session_id: uuid.UUID
    team_id: uuid.UUID
    message: str


@router.post("/{session_id}/join", response_model=JoinSessionResponse, status_code=201)
async def join_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.DRAFT_PENDING:
        raise HTTPException(status_code=409, detail="Session is not accepting new members")

    # Must be active member of the session's league
    if session.league_id is not None:
        lm_result = await db.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == session.league_id,
                LeagueMembership.user_id == current_user.id,
                LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
            )
        )
        if lm_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="Not a member of this session's league")

    # Check team count
    count_result = await db.execute(
        select(func.count()).select_from(Team).where(Team.session_id == session_id)
    )
    team_count = count_result.scalar_one()
    if team_count >= session.max_teams:
        raise HTTPException(status_code=409, detail="Session is full")

    # Check not already in session
    existing_result = await db.execute(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == current_user.id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already in this session")

    team = Team(
        session_id=session_id,
        name=current_user.display_name,
        type=TeamType.HUMAN,
        config={},
        faab_balance=100,
    )
    db.add(team)
    await db.flush()

    sm = SessionMembership(
        session_id=session_id,
        user_id=current_user.id,
        role=MembershipRole.MEMBER,
        team_id=team.id,
    )
    db.add(sm)
    await db.commit()

    return JoinSessionResponse(
        session_id=session_id,
        team_id=team.id,
        message="Joined session successfully",
    )


@router.post("/{session_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sm_result = await db.execute(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == current_user.id,
        )
    )
    sm = sm_result.scalar_one_or_none()
    if sm is None:
        raise HTTPException(status_code=404, detail="Not a member of this session")

    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=403, detail="Cannot leave a completed session")

    if session.status == SessionStatus.DRAFT_PENDING:
        if sm.team_id is not None:
            team_result = await db.execute(select(Team).where(Team.id == sm.team_id))
            team = team_result.scalar_one_or_none()
            if team:
                await db.delete(team)
        await db.delete(sm)
    elif session.status == SessionStatus.IN_PROGRESS:
        if sm.team_id is not None:
            team_result = await db.execute(select(Team).where(Team.id == sm.team_id))
            team = team_result.scalar_one_or_none()
            if team:
                team.type = "agent"
                team.config = _BOT_CONFIG

    await db.commit()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TeamSummary(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    faab_balance: int


class ScriptSummary(BaseModel):
    id: uuid.UUID
    sport: str
    season: int
    season_type: str
    total_events: int


class SessionDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    sport: str
    season: int
    status: str
    script_speed: str
    waiver_mode: str
    current_seq: int
    current_week: int
    is_running: bool
    script: ScriptSummary
    teams: list[TeamSummary]
    league_id: uuid.UUID | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_session_detail(
    session: Session,
    db: AsyncSession,
    runner_service: EventRunnerService,
) -> SessionDetailResponse:
    script = await db.get(SeasonScript, session.script_id)
    if script is None:
        raise HTTPException(status_code=500, detail="Session references a missing script")

    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = teams_result.scalars().all()

    # Determine current week from the nearest event before the cursor
    current_week = 1
    if session.current_seq > 0:
        week_row = await db.scalar(
            select(SeasonEvent.week_number)
            .where(
                SeasonEvent.script_id == session.script_id,
                SeasonEvent.seq < session.current_seq,
            )
            .order_by(SeasonEvent.seq.desc())
            .limit(1)
        )
        if week_row is not None:
            current_week = week_row

    return SessionDetailResponse(
        id=session.id,
        name=session.name,
        sport=session.sport,
        season=session.season,
        status=session.status,
        script_speed=session.script_speed,
        waiver_mode=session.waiver_mode,
        current_seq=session.current_seq,
        current_week=current_week,
        is_running=runner_service.is_running(session.id),
        script=ScriptSummary(
            id=script.id,
            sport=script.sport,
            season=script.season,
            season_type=script.season_type,
            total_events=script.total_events,
        ),
        teams=[
            TeamSummary(id=t.id, name=t.name, type=t.type, faab_balance=t.faab_balance)
            for t in teams
        ],
        league_id=session.league_id,
        created_at=session.created_at,
    )


# ---------------------------------------------------------------------------
# GET /{session_id}
# ---------------------------------------------------------------------------


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    runner_service: Annotated[EventRunnerService, Depends(get_runner_service)],
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Must be a member or observer
    sm = await db.scalar(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == current_user.id,
        )
    )
    if sm is None:
        raise HTTPException(status_code=403, detail="Not a member of this session")

    return await _build_session_detail(session, db, runner_service)


# ---------------------------------------------------------------------------
# POST /{session_id}/start
# ---------------------------------------------------------------------------


@router.post("/{session_id}/start", response_model=SessionDetailResponse)
async def start_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    runner_service: Annotated[EventRunnerService, Depends(get_runner_service)],
    db: AsyncSession = Depends(get_db),
):
    """
    Start (or resume) the EventRunner for a session.

    Allowed statuses: DRAFT_PENDING, PAUSED, IN_PROGRESS (idempotent resume).
    Only the session owner may start it.
    """
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the session owner can start it")

    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Session is already completed")

    # Already running — idempotent
    if runner_service.is_running(session_id):
        return await _build_session_detail(session, db, runner_service)

    # Load teams
    teams = await load_teams_for_session(session_id, session.league_id, db)
    if not teams:
        raise HTTPException(
            status_code=409,
            detail="Session has no teams with resolvable API keys — cannot start",
        )

    # Transition status
    if session.status != SessionStatus.IN_PROGRESS:
        session.status = SessionStatus.IN_PROGRESS
        if session.wall_start_time is None:
            session.wall_start_time = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)

    await runner_service.start(session_id, teams)

    return await _build_session_detail(session, db, runner_service)


# ---------------------------------------------------------------------------
# POST /{session_id}/pause
# ---------------------------------------------------------------------------


@router.post("/{session_id}/pause", response_model=SessionDetailResponse)
async def pause_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    runner_service: Annotated[EventRunnerService, Depends(get_runner_service)],
    db: AsyncSession = Depends(get_db),
):
    """Pause a running session. Only the owner may pause it."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the session owner can pause it")

    if not runner_service.is_running(session_id):
        raise HTTPException(status_code=409, detail="Session is not currently running")

    await runner_service.pause(session_id)

    session.status = SessionStatus.PAUSED
    await db.commit()
    await db.refresh(session)

    return await _build_session_detail(session, db, runner_service)


# ---------------------------------------------------------------------------
# DELETE /{session_id}
# ---------------------------------------------------------------------------


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    runner_service: Annotated[EventRunnerService, Depends(get_runner_service)],
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a session. Only the session owner or a league manager may do this.
    Running sessions are paused first.
    """
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    is_owner = session.owner_id == current_user.id

    # Also allow the league manager to delete
    is_league_manager = False
    if session.league_id:
        from backend.db.models import LeagueMembershipRole

        lm = await db.scalar(
            select(LeagueMembership).where(
                LeagueMembership.league_id == session.league_id,
                LeagueMembership.user_id == current_user.id,
                LeagueMembership.status == LeagueMembershipStatus.ACTIVE,
            )
        )
        is_league_manager = lm is not None and lm.role == LeagueMembershipRole.MANAGER

    if not is_owner and not is_league_manager:
        raise HTTPException(
            status_code=403, detail="Only the session owner or league manager can delete it"
        )

    # Stop runner if active
    if runner_service.is_running(session_id):
        await runner_service.pause(session_id)

    await db.delete(session)
    await db.commit()

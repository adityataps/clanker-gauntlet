"""
Lineup endpoints.

GET  /sessions/{session_id}/lineup  — team's current roster + starter flags + deadline
PUT  /sessions/{session_id}/lineup  — submit starter list for the current week
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.data.providers import sleeper
from backend.db.models import (
    AgentDecision,
    DecisionType,
    RosterPlayer,
    SeasonEvent,
    Session,
    SessionMembership,
    Team,
)
from backend.db.session import get_db

router = APIRouter(prefix="/sessions", tags=["lineup"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RosterPlayerResponse(BaseModel):
    player_id: str
    name: str
    position: str
    nfl_team: str | None
    projected_points: float | None
    status: str  # ACTIVE | QUESTIONABLE | DOUBTFUL | OUT | IR
    is_starter: bool


class LineupResponse(BaseModel):
    week: int
    deadline: str | None  # ISO timestamp, None if no lock upcoming
    locked: bool
    roster: list[RosterPlayerResponse]


class LineupSubmit(BaseModel):
    starters: list[str]  # player_ids
    week: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLEEPER_INJURY_MAP = {
    "Questionable": "QUESTIONABLE",
    "Doubtful": "DOUBTFUL",
    "Out": "OUT",
    "IR": "IR",
    "PUP": "IR",
}


async def _get_team_for_user(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Team:
    sm = await db.scalar(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == user_id,
        )
    )
    if sm is None or sm.team_id is None:
        raise HTTPException(status_code=403, detail="Not a member of this session")
    team = await db.get(Team, sm.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


# ---------------------------------------------------------------------------
# GET /{session_id}/lineup
# ---------------------------------------------------------------------------


@router.get("/{session_id}/lineup", response_model=LineupResponse)
async def get_lineup(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Return the current team's roster with player metadata and starter flags.

    - Metadata (name, position, team, injury status) from Sleeper player cache.
    - Projected points from Sleeper projections cache (current week).
    - Starters derived from the most recent lineup decision for this team.
    - Deadline from the next ROSTER_LOCK event not yet processed.
    """
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    team = await _get_team_for_user(session_id, current_user.id, db)

    # ── Roster player IDs ────────────────────────────────────────────────────

    roster_rows = await db.scalars(select(RosterPlayer).where(RosterPlayer.team_id == team.id))
    roster_players = list(roster_rows)

    if not roster_players:
        # Determine current week from cursor
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
        return LineupResponse(week=current_week, deadline=None, locked=False, roster=[])

    # ── Current week ─────────────────────────────────────────────────────────

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

    # ── Deadline: next ROSTER_LOCK event ─────────────────────────────────────

    deadline: str | None = None
    locked = False
    lock_event = await db.scalar(
        select(SeasonEvent)
        .where(
            SeasonEvent.script_id == session.script_id,
            SeasonEvent.event_type == "ROSTER_LOCK",
            SeasonEvent.seq >= session.current_seq,
        )
        .order_by(SeasonEvent.seq)
        .limit(1)
    )
    if (
        lock_event is not None
        and session.wall_start_time
        and lock_event.sim_offset_hours is not None
    ):
        cf = session.compression_factor or 1.0
        lock_wall = session.wall_start_time + timedelta(hours=lock_event.sim_offset_hours / cf)
        now = datetime.now(UTC)
        if lock_wall > now:
            deadline = lock_wall.isoformat()
        else:
            locked = True

    # If session is completed or past its last event, lock lineup
    if session.current_seq >= (
        await db.scalar(
            select(SeasonEvent.seq)
            .where(SeasonEvent.script_id == session.script_id)
            .order_by(SeasonEvent.seq.desc())
            .limit(1)
        )
        or 0
    ):
        locked = True

    # ── Starters: latest lineup decision for this team ───────────────────────

    latest_decision = await db.scalar(
        select(AgentDecision)
        .where(
            AgentDecision.session_id == session_id,
            AgentDecision.team_id == team.id,
            AgentDecision.decision_type == DecisionType.LINEUP,
        )
        .order_by(AgentDecision.created_at.desc())
        .limit(1)
    )

    starter_ids: set[str] = set()
    if latest_decision and latest_decision.payload:
        raw_starters = latest_decision.payload.get("starters", [])
        starter_ids = set(raw_starters)

    # ── Player metadata from Sleeper cache ───────────────────────────────────

    all_players = await sleeper.get_players()

    # ── Projections from Sleeper cache ───────────────────────────────────────

    projections: dict = {}
    with contextlib.suppress(Exception):
        projections = await sleeper.get_projections(
            season=session.season,
            week=current_week,
            season_type="regular",
        )

    # ── Build response ───────────────────────────────────────────────────────

    result: list[RosterPlayerResponse] = []
    for rp in roster_players:
        meta = all_players.get(rp.player_id)
        if meta is None:
            # Unknown player — include with minimal data
            result.append(
                RosterPlayerResponse(
                    player_id=rp.player_id,
                    name=rp.player_id,
                    position="?",
                    nfl_team=None,
                    projected_points=None,
                    status="ACTIVE",
                    is_starter=rp.player_id in starter_ids,
                )
            )
            continue

        injury_raw = meta.injury_status or ""
        status = _SLEEPER_INJURY_MAP.get(injury_raw, "ACTIVE")

        proj = projections.get(rp.player_id)
        projected_pts = proj.pts_half_ppr if proj else None

        result.append(
            RosterPlayerResponse(
                player_id=rp.player_id,
                name=meta.full_name or f"{meta.first_name or ''} {meta.last_name or ''}".strip(),
                position=meta.position or "?",
                nfl_team=meta.team,
                projected_points=projected_pts,
                status=status,
                is_starter=rp.player_id in starter_ids,
            )
        )

    # Sort: starters first, then by position priority
    _POS_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
    result.sort(
        key=lambda p: (
            0 if p.is_starter else 1,
            _POS_ORDER.get(p.position, 9),
        )
    )

    return LineupResponse(
        week=current_week,
        deadline=deadline,
        locked=locked,
        roster=result,
    )


# ---------------------------------------------------------------------------
# PUT /{session_id}/lineup
# ---------------------------------------------------------------------------


@router.put("/{session_id}/lineup", status_code=200)
async def set_lineup(
    session_id: uuid.UUID,
    body: LineupSubmit,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Submit the starter list for the current week.

    Validates all starters are on the team's roster. Stores the decision as an
    agent_decision record so it is visible in the decisions panel and picked up
    by the EventRunner when HumanTeam is wired in Phase 2.
    """
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    team = await _get_team_for_user(session_id, current_user.id, db)

    # Validate all starters are on this team's roster
    roster_rows = await db.scalars(select(RosterPlayer).where(RosterPlayer.team_id == team.id))
    owned_ids = {rp.player_id for rp in roster_rows}
    invalid = [pid for pid in body.starters if pid not in owned_ids]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Players not on roster: {invalid}",
        )

    # Persist as an agent decision (human acting as an agent)
    decision = AgentDecision(
        session_id=session_id,
        team_id=team.id,
        seq=session.current_seq,
        decision_type=DecisionType.LINEUP,
        payload={"starters": body.starters, "week": body.week},
        reasoning_trace={"summary": "Human lineup submission", "structured": None},
        tokens_used=0,
    )
    db.add(decision)
    await db.commit()

    return {"ok": True, "starters": body.starters, "week": body.week}

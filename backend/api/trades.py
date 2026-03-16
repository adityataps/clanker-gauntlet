"""
Trade endpoints.

POST /sessions/{session_id}/trades      propose a trade
GET  /sessions/{session_id}/trades      list trades in a session
GET  /trades/{trade_id}                 get a single trade
POST /trades/{trade_id}/respond         accept or reject (receiving team)
POST /trades/{trade_id}/cancel          cancel (proposing team only)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import (
    RosterPlayer,
    Session,
    SessionMembership,
    Team,
    TradeLock,
    TradeProposal,
    TradeStatus,
)
from backend.db.session import get_db
from backend.league.trades import acquire_locks, execute_roster_swap, release_locks

router = APIRouter(tags=["trades"])

_DEFAULT_EXPIRY_HOURS = 48


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProposeTradeRequest(BaseModel):
    receiving_team_id: uuid.UUID
    offered_player_ids: list[str]
    requested_player_ids: list[str]
    note: str | None = None
    expires_hours: int = _DEFAULT_EXPIRY_HOURS


class RespondTradeRequest(BaseModel):
    accept: bool


class TradeLockInfo(BaseModel):
    player_id: str
    locked_until: datetime


class TradeResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    proposing_team_id: uuid.UUID
    receiving_team_id: uuid.UUID
    offered_player_ids: list[str]
    requested_player_ids: list[str]
    status: TradeStatus
    note: str | None
    proposed_at: datetime
    resolved_at: datetime | None
    locks: list[TradeLockInfo]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_proposal_or_404(trade_id: uuid.UUID, db: AsyncSession) -> TradeProposal:
    result = await db.execute(select(TradeProposal).where(TradeProposal.id == trade_id))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Trade proposal not found")
    return proposal


async def _team_for_user(session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Team:
    """Return the team belonging to this user in this session."""
    sm_result = await db.execute(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == user_id,
        )
    )
    sm = sm_result.scalar_one_or_none()
    if sm is None or sm.team_id is None:
        raise HTTPException(status_code=403, detail="You do not have a team in this session")
    team_result = await db.execute(select(Team).where(Team.id == sm.team_id))
    return team_result.scalar_one()


async def _current_week(session_id: uuid.UUID, db: AsyncSession) -> int:
    """Best-effort: derive current week from the session's compiled script cursor."""
    from backend.db.models import SeasonEvent
    from backend.db.models import Session as SessionModel

    sess_result = await db.execute(select(SessionModel).where(SessionModel.id == session_id))
    sess = sess_result.scalar_one_or_none()
    if sess is None or sess.current_seq == 0:
        return 1
    ev_result = await db.execute(
        select(SeasonEvent.week_number)
        .where(
            SeasonEvent.script_id == sess.script_id,
            SeasonEvent.seq <= sess.current_seq,
        )
        .order_by(SeasonEvent.seq.desc())
        .limit(1)
    )
    row = ev_result.scalar_one_or_none()
    return row or 1


def _trade_response(proposal: TradeProposal, locks: list[TradeLock]) -> TradeResponse:
    return TradeResponse(
        id=proposal.id,
        session_id=proposal.session_id,
        proposing_team_id=proposal.proposing_team_id,
        receiving_team_id=proposal.receiving_team_id,
        offered_player_ids=proposal.offered_player_ids,
        requested_player_ids=proposal.requested_player_ids,
        status=proposal.status,
        note=proposal.note,
        proposed_at=proposal.proposed_at,
        resolved_at=proposal.resolved_at,
        locks=[TradeLockInfo(player_id=lk.player_id, locked_until=lk.locked_until) for lk in locks],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/trades",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_trade(
    session_id: uuid.UUID,
    body: ProposeTradeRequest,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Propose a trade. Acquires soft locks on all involved players."""
    sess_result = await db.execute(select(Session).where(Session.id == session_id))
    session = sess_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    proposing_team = await _team_for_user(session_id, current_user.id, db)

    if proposing_team.id == body.receiving_team_id:
        raise HTTPException(status_code=422, detail="Cannot trade with yourself")

    if not body.offered_player_ids or not body.requested_player_ids:
        raise HTTPException(status_code=422, detail="Both sides of the trade must include players")

    # Validate offered players are on the proposing team's roster
    offered_result = await db.execute(
        select(RosterPlayer.player_id).where(
            RosterPlayer.team_id == proposing_team.id,
            RosterPlayer.player_id.in_(body.offered_player_ids),
        )
    )
    owned_offered = {row[0] for row in offered_result.all()}
    not_owned = set(body.offered_player_ids) - owned_offered
    if not_owned:
        raise HTTPException(
            status_code=422, detail=f"You do not own these players: {sorted(not_owned)}"
        )

    # Validate requested players are on the receiving team's roster
    requested_result = await db.execute(
        select(RosterPlayer.player_id).where(
            RosterPlayer.team_id == body.receiving_team_id,
            RosterPlayer.player_id.in_(body.requested_player_ids),
        )
    )
    owned_requested = {row[0] for row in requested_result.all()}
    not_on_other = set(body.requested_player_ids) - owned_requested
    if not_on_other:
        raise HTTPException(
            status_code=422,
            detail=f"The other team does not own these players: {sorted(not_on_other)}",
        )

    all_player_ids = list(set(body.offered_player_ids) | set(body.requested_player_ids))
    locked_until = datetime.now(UTC) + timedelta(hours=body.expires_hours)

    # Create proposal first (need its ID for lock FK)
    proposal = TradeProposal(
        session_id=session_id,
        proposing_team_id=proposing_team.id,
        receiving_team_id=body.receiving_team_id,
        offered_player_ids=body.offered_player_ids,
        requested_player_ids=body.requested_player_ids,
        note=body.note,
        status=TradeStatus.PENDING,
    )
    db.add(proposal)
    await db.flush()  # get proposal.id

    conflicts = await acquire_locks(session_id, all_player_ids, proposal.id, locked_until, db)
    if conflicts:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Players already in a pending trade: {sorted(conflicts)}",
        )

    await db.commit()
    await db.refresh(proposal)

    locks_result = await db.execute(
        select(TradeLock).where(TradeLock.trade_proposal_id == proposal.id)
    )
    return _trade_response(proposal, locks_result.scalars().all())


@router.get("/sessions/{session_id}/trades", response_model=list[TradeResponse])
async def list_trades(
    session_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """List all trades in a session. Must be a session member."""
    sm_result = await db.execute(
        select(SessionMembership).where(
            SessionMembership.session_id == session_id,
            SessionMembership.user_id == current_user.id,
        )
    )
    if sm_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of this session")

    proposals_result = await db.execute(
        select(TradeProposal).where(TradeProposal.session_id == session_id)
    )
    proposals = proposals_result.scalars().all()

    out = []
    for p in proposals:
        locks_result = await db.execute(
            select(TradeLock).where(TradeLock.trade_proposal_id == p.id)
        )
        out.append(_trade_response(p, locks_result.scalars().all()))
    return out


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    proposal = await _get_proposal_or_404(trade_id, db)

    # Must be a member of the session
    sm_result = await db.execute(
        select(SessionMembership).where(
            SessionMembership.session_id == proposal.session_id,
            SessionMembership.user_id == current_user.id,
        )
    )
    if sm_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member of this session")

    locks_result = await db.execute(
        select(TradeLock).where(TradeLock.trade_proposal_id == trade_id)
    )
    return _trade_response(proposal, locks_result.scalars().all())


@router.post("/trades/{trade_id}/respond", response_model=TradeResponse)
async def respond_to_trade(
    trade_id: uuid.UUID,
    body: RespondTradeRequest,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Accept or reject a trade proposal. Only the receiving team can respond."""
    proposal = await _get_proposal_or_404(trade_id, db)

    if proposal.status != TradeStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Trade is already {proposal.status}")

    receiving_team = await _team_for_user(proposal.session_id, current_user.id, db)
    if receiving_team.id != proposal.receiving_team_id:
        raise HTTPException(
            status_code=403, detail="Only the receiving team can respond to this trade"
        )

    now = datetime.now(UTC)

    if body.accept:
        week = await _current_week(proposal.session_id, db)
        await execute_roster_swap(proposal, week, db)
        proposal.status = TradeStatus.ACCEPTED
    else:
        proposal.status = TradeStatus.REJECTED

    proposal.resolved_at = now
    await release_locks(proposal.id, db)
    await db.commit()
    await db.refresh(proposal)

    return _trade_response(proposal, [])


@router.post("/trades/{trade_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_trade(
    trade_id: uuid.UUID,
    current_user: Annotated[object, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending trade. Only the proposing team can cancel."""
    proposal = await _get_proposal_or_404(trade_id, db)

    if proposal.status != TradeStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Trade is already {proposal.status}")

    proposing_team = await _team_for_user(proposal.session_id, current_user.id, db)
    if proposing_team.id != proposal.proposing_team_id:
        raise HTTPException(status_code=403, detail="Only the proposing team can cancel this trade")

    proposal.status = TradeStatus.CANCELLED
    proposal.resolved_at = datetime.now(UTC)
    await release_locks(proposal.id, db)
    await db.commit()

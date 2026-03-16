import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import (
    LeagueMembership,
    LeagueMembershipStatus,
    MembershipRole,
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

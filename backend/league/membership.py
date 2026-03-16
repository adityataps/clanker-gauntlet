import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    LeagueMembership,
    LeagueMembershipStatus,
    Session,
    SessionMembership,
    SessionStatus,
    Team,
)

_BOT_CONFIG = {
    "archetype": "analytician",
    "reasoning_depth": "standard",
    "provider": "anthropic",
}


async def handle_member_exit(
    league_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    status: LeagueMembershipStatus,
) -> None:
    # Find all session memberships for this user in sessions belonging to this league
    stmt = (
        select(SessionMembership, Session)
        .join(Session, Session.id == SessionMembership.session_id)
        .where(
            SessionMembership.user_id == user_id,
            Session.league_id == league_id,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    for sm, session in rows:
        if session.status == SessionStatus.DRAFT_PENDING:
            # Remove the team and the membership
            if sm.team_id is not None:
                team_result = await db.execute(select(Team).where(Team.id == sm.team_id))
                team = team_result.scalar_one_or_none()
                if team:
                    await db.delete(team)
            await db.delete(sm)
        elif session.status == SessionStatus.IN_PROGRESS:
            # Convert team to a bot
            if sm.team_id is not None:
                team_result = await db.execute(select(Team).where(Team.id == sm.team_id))
                team = team_result.scalar_one_or_none()
                if team:
                    team.type = "agent"
                    team.config = _BOT_CONFIG
        # COMPLETED: do nothing

    # Update league membership status
    lm_result = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.user_id == user_id,
        )
    )
    lm = lm_result.scalar_one_or_none()
    if lm:
        lm.status = status
        lm.left_at = datetime.now(UTC)

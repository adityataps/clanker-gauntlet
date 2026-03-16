"""
Trade soft-locking and execution service.

Lock lifecycle:
    acquire_locks()  — called at proposal creation; returns conflicting player IDs
                       (empty list = all locks acquired successfully)
    release_locks()  — called at resolution (accept/reject/cancel/expire)
    expire_stale_locks() — lazy cleanup; called before any lock check

Roster swap:
    execute_roster_swap() — atomically moves players between teams on accept
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AcquiredVia, RosterPlayer, TradeLock, TradeProposal


async def expire_stale_locks(session_id: uuid.UUID, db: AsyncSession) -> None:
    """Delete locks whose locked_until has passed."""
    await db.execute(
        delete(TradeLock).where(
            TradeLock.session_id == session_id,
            TradeLock.locked_until < datetime.now(UTC),
        )
    )


async def get_conflicting_locks(
    session_id: uuid.UUID, player_ids: list[str], db: AsyncSession
) -> list[str]:
    """Return any player IDs from the list that are currently locked."""
    await expire_stale_locks(session_id, db)
    result = await db.execute(
        select(TradeLock.player_id).where(
            TradeLock.session_id == session_id,
            TradeLock.player_id.in_(player_ids),
        )
    )
    return [row[0] for row in result.all()]


async def acquire_locks(
    session_id: uuid.UUID,
    player_ids: list[str],
    proposal_id: uuid.UUID,
    locked_until: datetime,
    db: AsyncSession,
) -> list[str]:
    """
    Acquire locks for all player_ids atomically.

    Returns a list of conflicting player IDs. Empty list means all locks
    were acquired and the proposal can proceed.
    """
    conflicts = await get_conflicting_locks(session_id, player_ids, db)
    if conflicts:
        return conflicts

    for player_id in player_ids:
        db.add(
            TradeLock(
                player_id=player_id,
                session_id=session_id,
                trade_proposal_id=proposal_id,
                locked_until=locked_until,
            )
        )
    return []


async def release_locks(proposal_id: uuid.UUID, db: AsyncSession) -> None:
    """Release all locks held by a trade proposal."""
    await db.execute(delete(TradeLock).where(TradeLock.trade_proposal_id == proposal_id))


async def execute_roster_swap(
    proposal: TradeProposal,
    current_week: int,
    db: AsyncSession,
) -> None:
    """
    Swap roster players between the two teams.

    Offered players move from proposing_team → receiving_team.
    Requested players move from receiving_team → proposing_team.
    """
    transfers = [
        (proposal.offered_player_ids, proposal.proposing_team_id, proposal.receiving_team_id),
        (proposal.requested_player_ids, proposal.receiving_team_id, proposal.proposing_team_id),
    ]
    for player_ids, from_team_id, to_team_id in transfers:
        for player_id in player_ids:
            result = await db.execute(
                select(RosterPlayer).where(
                    RosterPlayer.team_id == from_team_id,
                    RosterPlayer.player_id == player_id,
                )
            )
            rp = result.scalar_one_or_none()
            if rp is not None:
                rp.team_id = to_team_id
                rp.acquired_week = current_week
                rp.acquired_via = AcquiredVia.TRADE

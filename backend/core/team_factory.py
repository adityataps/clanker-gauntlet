"""
Team factory — loads Team rows from DB and instantiates protocol objects.

Called by the session-start endpoint just before handing teams to the
EventRunnerService. Returns a ready-to-use dict[team_id → BaseTeam].

Team type handling:
    AGENT   Built with three-tier key resolution using the associated user
            (via SessionMembership). Agent-only teams with no user (user_id=None)
            skip tier 1 and resolve via league or system key.
    HUMAN   Phase 2. Currently auto-piloted by an AgentTeam with the
            analytician archetype + the user's resolved key. PendingDecision
            / UI-backed decisions land in Phase 2.
    EXTERNAL Phase 3. Skipped with a warning for now.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.llm_factory import build_llm_client_for_agent
from backend.db.models import SessionMembership, Team, TeamType
from backend.teams.agent_team import AgentTeam
from backend.teams.protocol import BaseTeam

logger = logging.getLogger(__name__)

_DEFAULT_ARCHETYPE = "analytician"
_DEFAULT_PROVIDER = "anthropic"
_DEFAULT_DEPTH = "standard"


async def load_teams_for_session(
    session_id: uuid.UUID,
    league_id: uuid.UUID | None,
    db: AsyncSession,
) -> dict[uuid.UUID, BaseTeam]:
    """
    Load all Team rows for a session and return team_id → BaseTeam.

    Skips teams whose API key cannot be resolved (logs an error per team).
    Returns an empty dict if the session has no teams.
    """
    team_rows = (
        (await db.execute(select(Team).where(Team.session_id == session_id))).scalars().all()
    )

    if not team_rows:
        logger.warning("No teams found for session %s", session_id)
        return {}

    # Build team_id → user_id from session memberships
    memberships = (
        (
            await db.execute(
                select(SessionMembership).where(SessionMembership.session_id == session_id)
            )
        )
        .scalars()
        .all()
    )
    user_by_team: dict[uuid.UUID, uuid.UUID | None] = {
        sm.team_id: sm.user_id for sm in memberships if sm.team_id is not None
    }

    teams: dict[uuid.UUID, BaseTeam] = {}

    for row in team_rows:
        if row.type == TeamType.EXTERNAL:
            logger.warning("ExternalTeam not yet implemented — skipping team %s", row.id)
            continue

        cfg = row.config or {}
        archetype = cfg.get("archetype", _DEFAULT_ARCHETYPE)
        provider = cfg.get("provider", _DEFAULT_PROVIDER)
        depth = cfg.get("reasoning_depth", _DEFAULT_DEPTH)
        user_id = user_by_team.get(row.id)  # None for system-managed agents

        try:
            agent_client = await build_llm_client_for_agent(
                user_id=user_id,
                league_id=league_id,
                provider=provider,
                reasoning_depth=depth,
                db=db,
            )
        except ValueError as exc:
            logger.error(
                "Cannot resolve API key for team %s (user=%s provider=%s): %s — skipping",
                row.id,
                user_id,
                provider,
                exc,
            )
            continue

        team = AgentTeam(
            team_id=row.id,
            name=row.name,
            archetype=archetype,
            llm_client=agent_client.client,
            session_id=session_id,
        )
        teams[row.id] = team

        logger.info(
            "Team %s (%s) loaded: archetype=%s provider=%s tier=%s",
            row.id,
            row.name,
            archetype,
            provider,
            agent_client.tier,
        )

    return teams

"""
Decision context models and decision output models.

These Pydantic models are passed between the EventRunner and teams at each
decision point. The runner builds the context; the team returns a decision.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class RosterEntry(BaseModel):
    """A player on a team's roster."""

    player_id: str
    slot: str  # "active" | "bench" | "ir"
    acquired_week: int
    acquired_via: str  # "draft" | "waiver" | "trade"


class LineupDecision(BaseModel):
    """Team's submitted starting lineup."""

    starters: list[str]  # player_ids
    reasoning: str | None = None


class WaiverBid(BaseModel):
    """A single FAAB bid for the waiver auction."""

    add_player_id: str
    drop_player_id: str | None = None
    bid_amount: int = Field(default=0, ge=0)  # 0 = no bid (priority mode); required for FAAB
    priority: int = Field(ge=1)  # 1 = top choice


class TradeDecision(BaseModel):
    """Team's response to a trade proposal."""

    accept: bool
    reasoning: str | None = None


class WaiverPlayerInfo(BaseModel):
    """Player available on the waiver wire."""

    player_id: str
    name: str
    position: str
    nfl_team: str | None = None
    projected_points: float | None = None


class WeekContext(BaseModel):
    """Context passed to a team at lineup decision time."""

    session_id: uuid.UUID
    team_id: uuid.UUID
    week: int
    season: int
    sport: str
    roster: list[RosterEntry]
    projections: dict[str, Any] = Field(default_factory=dict)  # player_id -> projection data
    recent_news: list[dict] = Field(default_factory=list)
    faab_balance: int = 100
    scoring_config: dict = Field(default_factory=dict)


class WaiverContext(BaseModel):
    """Context passed to a team during the waiver window."""

    session_id: uuid.UUID
    team_id: uuid.UUID
    week: int
    season: int
    sport: str
    roster: list[RosterEntry]
    waiver_wire: list[WaiverPlayerInfo] = Field(default_factory=list)
    projections: dict[str, Any] = Field(default_factory=dict)
    recent_news: list[dict] = Field(default_factory=list)
    faab_balance: int = 100


class TradeProposalInfo(BaseModel):
    """Trade proposal details passed to the receiving team."""

    proposal_id: uuid.UUID
    proposing_team_id: uuid.UUID
    proposing_team_name: str
    offered_player_ids: list[str]
    requested_player_ids: list[str]
    note: str | None = None


class TradeContext(BaseModel):
    """Context passed to a team when evaluating an incoming trade."""

    session_id: uuid.UUID
    team_id: uuid.UUID  # the receiving team
    week: int
    season: int
    sport: str
    roster: list[RosterEntry]
    proposal: TradeProposalInfo
    projections: dict[str, Any] = Field(default_factory=dict)

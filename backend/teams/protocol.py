"""
Team protocol — abstract base class all team types must implement.

The EventRunner only interacts with teams through this interface.
AgentTeam, HumanTeam, and ExternalTeam all subclass BaseTeam.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from backend.teams.context import (
    LineupDecision,
    TradeContext,
    TradeDecision,
    WaiverBid,
    WaiverContext,
    WeekContext,
)


class BaseTeam(ABC):
    """Abstract base for all team types."""

    def __init__(self, team_id: uuid.UUID, name: str) -> None:
        self.team_id = team_id
        self.name = name

    @abstractmethod
    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision:
        """Submit the starting lineup for a week. Called at AGENT_WINDOW_OPEN type=lineup."""
        ...

    @abstractmethod
    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]:
        """Submit FAAB bids for the waiver window. Called at AGENT_WINDOW_OPEN type=waiver."""
        ...

    @abstractmethod
    async def evaluate_trade(self, ctx: TradeContext) -> TradeDecision:
        """Accept or reject an incoming trade proposal."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.team_id}, name={self.name!r})"

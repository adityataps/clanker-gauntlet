"""
Pydantic models for data flowing through the system.
These are transport/domain models — separate from SQLAlchemy ORM models.

Player metadata is never stored in the DB; it always comes from the
Sleeper API (or Redis cache). Only player_id strings are persisted.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


class Player(BaseModel):
    """
    NFL player from the Sleeper player universe.
    Sleeper returns many fields; extras are silently ignored.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    player_id: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    position: str | None = None  # QB | RB | WR | TE | K | DEF
    fantasy_positions: list[str] = Field(default_factory=list)
    team: str | None = None  # NFL team abbreviation e.g. "SF", "KC"
    status: str | None = None  # Active | Inactive | IR | PUP
    injury_status: str | None = None  # Questionable | Doubtful | Out | IR
    age: int | None = None
    years_exp: int | None = None
    number: int | None = None
    depth_chart_order: int | None = None

    @field_validator("fantasy_positions", mode="before")
    @classmethod
    def coerce_fantasy_positions(cls, v: object) -> list:
        # Sleeper sometimes returns null instead of []
        return v if isinstance(v, list) else []

    @property
    def display_name(self) -> str:
        return (
            self.full_name
            or f"{self.first_name or ''} {self.last_name or ''}".strip()
            or self.player_id
        )

    @property
    def is_available(self) -> bool:
        """False if the player is on IR or otherwise unavailable."""
        return self.status not in ("Inactive", "IR", "PUP", "Suspended")


# ---------------------------------------------------------------------------
# Stats & Projections
# ---------------------------------------------------------------------------

_STAT_FIELDS = {
    # Fantasy totals
    "pts_half_ppr",
    "pts_ppr",
    "pts_std",
    # Passing
    "pass_yd",
    "pass_td",
    "pass_int",
    "pass_att",
    "pass_cmp",
    "pass_2pt",
    # Rushing
    "rush_yd",
    "rush_td",
    "rush_att",
    "rush_2pt",
    # Receiving
    "rec",
    "rec_yd",
    "rec_td",
    "rec_tgt",
    "rec_2pt",
    # Misc / special teams
    "fum_lost",
    "ret_td",
    "bonus_rec_te",
}


class PlayerStats(BaseModel):
    """
    Actual weekly stats for a player (post-game actuals from Sleeper).
    Unknown stat fields from Sleeper are passed through via `extra`.
    """

    model_config = ConfigDict(extra="allow")

    player_id: str
    week: int
    season: int
    season_type: str = "regular"

    # Fantasy points
    pts_half_ppr: float | None = None
    pts_ppr: float | None = None
    pts_std: float | None = None

    # Passing
    pass_yd: float | None = None
    pass_td: float | None = None
    pass_int: float | None = None
    pass_att: float | None = None
    pass_cmp: float | None = None

    # Rushing
    rush_yd: float | None = None
    rush_td: float | None = None
    rush_att: float | None = None

    # Receiving
    rec: float | None = None
    rec_yd: float | None = None
    rec_td: float | None = None
    rec_tgt: float | None = None

    # Misc
    fum_lost: float | None = None


class Projection(BaseModel):
    """
    Projected weekly stats for a player (from Sleeper projections endpoint).
    Same shape as PlayerStats — same stat field names, forward-looking values.
    """

    model_config = ConfigDict(extra="allow")

    player_id: str
    week: int
    season: int
    season_type: str = "regular"

    pts_half_ppr: float | None = None
    pts_ppr: float | None = None
    pts_std: float | None = None

    pass_yd: float | None = None
    pass_td: float | None = None
    pass_int: float | None = None
    pass_att: float | None = None
    pass_cmp: float | None = None

    rush_yd: float | None = None
    rush_td: float | None = None
    rush_att: float | None = None

    rec: float | None = None
    rec_yd: float | None = None
    rec_td: float | None = None
    rec_tgt: float | None = None


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


class NewsItem(BaseModel):
    """
    A news or injury item from an RSS feed or data provider.
    player_id is populated when we can match the item to a Sleeper player.
    """

    player_id: str | None = None
    player_name: str | None = None
    team: str | None = None
    headline: str
    body: str | None = None
    published_at: datetime
    source: str  # e.g. "rotoworld", "rotoballer"
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Game Events (compiled season script)
# ---------------------------------------------------------------------------


class GameEvent(BaseModel):
    """
    A single event in the compiled season script (season_events table).
    payload shape varies by event_type — see EventRunner for each type's schema.
    """

    seq: int
    event_type: str
    week_number: int
    sim_offset_hours: float  # hours from season kickoff
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Waiver wire helpers
# ---------------------------------------------------------------------------


class WaiverPlayer(BaseModel):
    """A player on the waiver wire with context for agent decision-making."""

    player: Player
    projection: Projection | None = None
    trend_adds: int = 0  # how many leagues added this player recently
    available_in_session: bool = True

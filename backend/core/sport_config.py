"""
SportConfig — loads sport configuration from config/sports/<sport>.yaml.

Contains scoring rules and roster settings. Scoring rules can be overridden
per session via sessions.scoring_config JSONB (merged at load time).
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "sports"


class PtsAllowTier(BaseModel):
    """One tier of the DEF points-allowed scoring table."""

    max: int
    pts: float


class ScoringConfig(BaseModel):
    """
    Per-stat scoring multipliers and special-case rules.
    Defaults match standard 0.5 PPR.
    """

    # Passing
    pass_yd: float = 0.04
    pass_td: float = 4.0
    pass_int: float = -2.0
    pass_2pt: float = 2.0
    pass_sack: float = 0.0

    # Rushing
    rush_yd: float = 0.1
    rush_td: float = 6.0
    rush_2pt: float = 2.0

    # Receiving
    rec: float = 0.5
    rec_yd: float = 0.1
    rec_td: float = 6.0
    rec_2pt: float = 2.0

    # Misc
    fum_lost: float = -2.0
    ret_td: float = 6.0

    # Kicker
    xpm: float = 1.0
    fgm_0_19: float = 3.0
    fgm_20_29: float = 3.0
    fgm_30_39: float = 3.0
    fgm_40_49: float = 4.0
    fgm_50_59: float = 5.0
    fgm_60_plus: float = 6.0
    fgmiss: float = -1.0

    # DEF per-play
    sack: float = 1.0
    int: float = 2.0
    fum_rec: float = 2.0
    def_td: float = 6.0
    safe: float = 2.0
    blk_kick: float = 2.0

    # DEF tiered points-allowed (evaluated separately in engine)
    pts_allow_tiers: list[PtsAllowTier] = Field(default_factory=list)

    def pts_allowed_score(self, pts_allowed: int) -> float:
        """Return fantasy points for a DEF given how many points they allowed."""
        for tier in self.pts_allow_tiers:
            if pts_allowed <= tier.max:
                return tier.pts
        return -4.0  # fallback: 35+ points allowed

    def with_overrides(self, overrides: dict) -> "ScoringConfig":
        """Return a new ScoringConfig with the given fields overridden."""
        return self.model_copy(update=overrides)


class RosterConfig(BaseModel):
    """Roster slot definitions for the sport."""

    slots: list[str] = Field(default_factory=list)
    flex_positions: list[str] = Field(default_factory=list)
    bench_slots: int = 6
    ir_slots: int = 1
    max_teams: int = 12

    @property
    def starting_slots(self) -> list[str]:
        """Slots that count toward the starting lineup (excludes bench/IR)."""
        return self.slots


class SportConfig(BaseModel):
    """Full configuration for a sport, loaded from YAML."""

    sport: str
    scoring: ScoringConfig
    roster: RosterConfig

    @classmethod
    def load(cls, sport: str) -> "SportConfig":
        path = _CONFIG_DIR / f"{sport}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"No sport config found at {path}")
        raw = yaml.safe_load(path.read_text())
        return cls(**raw)

    @classmethod
    def load_with_overrides(cls, sport: str, overrides: dict) -> "SportConfig":
        """Load base config then apply session-level scoring overrides."""
        config = cls.load(sport)
        if overrides:
            config = config.model_copy(update={"scoring": config.scoring.with_overrides(overrides)})
        return config

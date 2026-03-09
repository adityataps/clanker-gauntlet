"""
Scoring engine — converts raw player stats into fantasy points.

This is a pure module: no DB, no async, no side effects.
Takes a stats dict (Sleeper field names) + ScoringConfig → float.

The engine handles three player types:
  - Skill positions (QB, RB, WR, TE): standard per-stat multipliers
  - Kicker (K):                       per-distance FG + XP scoring
  - Defense (DEF):                    per-play stats + tiered pts-allowed

Usage:
    from backend.core.sport_config import SportConfig
    from backend.league.engine import calculate_points

    config = SportConfig.load("nfl")
    pts = calculate_points({"rec": 7, "rec_yd": 89, "rec_td": 1}, config.scoring)
    # → 22.9
"""

from backend.core.sport_config import ScoringConfig

# Skill-position stat fields and their ScoringConfig attribute names (1:1 mapping)
_SKILL_STAT_FIELDS: list[tuple[str, str]] = [
    # (sleeper_field, scoring_config_attr)
    ("pass_yd", "pass_yd"),
    ("pass_td", "pass_td"),
    ("pass_int", "pass_int"),
    ("pass_2pt", "pass_2pt"),
    ("rush_yd", "rush_yd"),
    ("rush_td", "rush_td"),
    ("rush_2pt", "rush_2pt"),
    ("rec", "rec"),
    ("rec_yd", "rec_yd"),
    ("rec_td", "rec_td"),
    ("rec_2pt", "rec_2pt"),
    ("fum_lost", "fum_lost"),
    ("ret_td", "ret_td"),
]

# Kicker stat fields
_KICKER_STAT_FIELDS: list[tuple[str, str]] = [
    ("xpm", "xpm"),
    ("fgm_0_19", "fgm_0_19"),
    ("fgm_20_29", "fgm_20_29"),
    ("fgm_30_39", "fgm_30_39"),
    ("fgm_40_49", "fgm_40_49"),
    ("fgm_50_59", "fgm_50_59"),
    ("fgm_60_plus", "fgm_60_plus"),
    ("fgmiss", "fgmiss"),
]

# DEF per-play stat fields
# Note: Sleeper uses "td" for DEF touchdowns (not "def_td")
_DEF_STAT_FIELDS: list[tuple[str, str]] = [
    ("sack", "sack"),
    ("int", "int"),
    ("fum_rec", "fum_rec"),
    ("td", "def_td"),  # Sleeper uses "td" for DEF
    ("safe", "safe"),
    ("blk_kick", "blk_kick"),
]


def calculate_points(
    stats: dict[str, float | int | None],
    scoring: ScoringConfig,
    position: str | None = None,
) -> float:
    """
    Calculate half-PPR fantasy points for a player from their raw stats.

    Args:
        stats:    Sleeper-format stats dict (field → value).
        scoring:  ScoringConfig (from SportConfig.load("nfl").scoring).
        position: Player position hint ("K", "DEF", or skill). If None,
                  the engine auto-detects based on which stat fields are present.

    Returns:
        Fantasy points rounded to 2 decimal places.
    """
    pts = 0.0

    # Auto-detect position if not provided
    if position is None:
        if "pts_allow" in stats or "sack" in stats:
            position = "DEF"
        elif "xpm" in stats or any(f.startswith("fgm_") for f in stats):
            position = "K"

    if position == "DEF":
        pts += _score_def(stats, scoring)
    elif position == "K":
        pts += _score_kicker(stats, scoring)
    else:
        pts += _score_skill(stats, scoring)

    return round(pts, 2)


def calculate_points_from_event(payload: dict, scoring: ScoringConfig) -> float:
    """
    Convenience wrapper for scoring a SCORE_UPDATE event payload directly.
    payload shape: { player_id, pts_half_ppr, stats: { field: value } }
    """
    stats = payload.get("stats", {})
    return calculate_points(stats, scoring)


# ---------------------------------------------------------------------------
# Position-specific scorers
# ---------------------------------------------------------------------------


def _score_skill(stats: dict, scoring: ScoringConfig) -> float:
    """Score a skill-position player (QB / RB / WR / TE)."""
    pts = 0.0
    for sleeper_field, config_attr in _SKILL_STAT_FIELDS:
        val = stats.get(sleeper_field) or 0.0
        pts += val * getattr(scoring, config_attr)
    return pts


def _score_kicker(stats: dict, scoring: ScoringConfig) -> float:
    """Score a kicker."""
    pts = 0.0
    for sleeper_field, config_attr in _KICKER_STAT_FIELDS:
        val = stats.get(sleeper_field) or 0.0
        pts += val * getattr(scoring, config_attr)
    return pts


def _score_def(stats: dict, scoring: ScoringConfig) -> float:
    """Score a team defense / special teams unit."""
    pts = 0.0

    # Per-play stats
    for sleeper_field, config_attr in _DEF_STAT_FIELDS:
        val = stats.get(sleeper_field) or 0.0
        pts += val * getattr(scoring, config_attr)

    # Tiered points-allowed scoring
    pts_allow = stats.get("pts_allow")
    if pts_allow is not None:
        pts += scoring.pts_allowed_score(int(pts_allow))

    return pts

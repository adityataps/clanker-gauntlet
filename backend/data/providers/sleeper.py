"""
Sleeper API client.

All endpoints are unauthenticated. Base URL: https://api.sleeper.app/v1

Caching strategy:
  - Player universe  → disk file (data_cache/nfl_players.json) + Redis, TTL 24h
  - Projections      → Redis only, TTL 1h
  - Stats            → Redis only, TTL 30m
  - Trending adds    → Redis only, TTL 15m

The disk cache for the player universe means the app works offline after
first run, and survives Redis restarts without hammering Sleeper.
"""

import json
import logging
from pathlib import Path

import httpx

from backend.data.cache import (
    TTL_PLAYERS,
    TTL_PROJECTIONS,
    TTL_STATS,
    TTL_TRENDING,
    cache,
)
from backend.data.models import Player, PlayerStats, Projection

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sleeper.app/v1"

# Disk cache location — gitignored, recreated on first run
_DISK_CACHE_DIR = Path(__file__).resolve().parents[3] / "data_cache"
_PLAYERS_CACHE_FILE = _DISK_CACHE_DIR / "nfl_players.json"

_REDIS_KEY_PLAYERS = "sleeper:players:nfl"
_REDIS_KEY_PROJECTIONS = "sleeper:projections:nfl:{season_type}:{season}:{week}"
_REDIS_KEY_STATS = "sleeper:stats:nfl:{season_type}:{season}:{week}"
_REDIS_KEY_TRENDING = "sleeper:trending:nfl:add"


async def _get(path: str) -> dict | list:
    """Make a GET request to the Sleeper API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}{path}")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Player universe
# ---------------------------------------------------------------------------


async def get_players(force_refresh: bool = False) -> dict[str, Player]:
    """
    Return the full NFL player universe keyed by player_id.

    Cache hierarchy:
      1. Redis (TTL 24h)
      2. Disk file (data_cache/nfl_players.json)
      3. Sleeper API → write to both Redis and disk
    """
    if not force_refresh:
        # 1. Try Redis
        cached = await cache.get(_REDIS_KEY_PLAYERS)
        if cached:
            logger.debug("Player universe loaded from Redis cache")
            return {pid: Player(**{**data, "player_id": pid}) for pid, data in cached.items()}

        # 2. Try disk
        if _PLAYERS_CACHE_FILE.exists():
            logger.debug("Player universe loaded from disk cache")
            raw = json.loads(_PLAYERS_CACHE_FILE.read_text())
            await cache.set(_REDIS_KEY_PLAYERS, raw, TTL_PLAYERS)
            return {pid: Player(player_id=pid, **data) for pid, data in raw.items()}

    # 3. Fetch from Sleeper
    logger.info("Fetching player universe from Sleeper API...")
    raw: dict = await _get("/players/nfl")

    # Persist to disk and Redis
    _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _PLAYERS_CACHE_FILE.write_text(json.dumps(raw))
    await cache.set(_REDIS_KEY_PLAYERS, raw, TTL_PLAYERS)

    logger.info("Player universe cached (%d players)", len(raw))
    return {pid: Player(player_id=pid, **data) for pid, data in raw.items()}


async def get_player(player_id: str) -> Player | None:
    """Return a single player by Sleeper ID."""
    players = await get_players()
    return players.get(player_id)


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


async def get_projections(
    season: int,
    week: int,
    season_type: str = "regular",
) -> dict[str, Projection]:
    """
    Return weekly projections for all players, keyed by player_id.
    Cached in Redis for 1 hour.
    """
    key = _REDIS_KEY_PROJECTIONS.format(season_type=season_type, season=season, week=week)

    cached = await cache.get(key)
    if cached:
        return {
            pid: Projection(
                **{
                    **data,
                    "player_id": pid,
                    "week": week,
                    "season": season,
                    "season_type": season_type,
                }
            )
            for pid, data in cached.items()
        }

    logger.info(
        "Fetching projections from Sleeper: %s season %d week %d", season_type, season, week
    )
    raw: dict = await _get(f"/projections/nfl/{season_type}/{season}/{week}")

    await cache.set(key, raw, TTL_PROJECTIONS)
    return {
        pid: Projection(
            **{**data, "player_id": pid, "week": week, "season": season, "season_type": season_type}
        )
        for pid, data in raw.items()
    }


async def get_projection(
    player_id: str,
    season: int,
    week: int,
    season_type: str = "regular",
) -> Projection | None:
    """Return projection for a single player."""
    projections = await get_projections(season, week, season_type)
    return projections.get(player_id)


# ---------------------------------------------------------------------------
# Stats (actuals)
# ---------------------------------------------------------------------------


async def get_stats(
    season: int,
    week: int,
    season_type: str = "regular",
) -> dict[str, PlayerStats]:
    """
    Return actual weekly stats for all players, keyed by player_id.
    Cached in Redis for 30 minutes.
    """
    key = _REDIS_KEY_STATS.format(season_type=season_type, season=season, week=week)

    cached = await cache.get(key)
    if cached:
        return {
            pid: PlayerStats(
                **{
                    **data,
                    "player_id": pid,
                    "week": week,
                    "season": season,
                    "season_type": season_type,
                }
            )
            for pid, data in cached.items()
        }

    logger.info("Fetching stats from Sleeper: %s season %d week %d", season_type, season, week)
    raw: dict = await _get(f"/stats/nfl/{season_type}/{season}/{week}")

    await cache.set(key, raw, TTL_STATS)
    return {
        pid: PlayerStats(
            **{**data, "player_id": pid, "week": week, "season": season, "season_type": season_type}
        )
        for pid, data in raw.items()
    }


async def get_player_stats(
    player_id: str,
    season: int,
    week: int,
    season_type: str = "regular",
) -> PlayerStats | None:
    """Return actual stats for a single player."""
    stats = await get_stats(season, week, season_type)
    return stats.get(player_id)


# ---------------------------------------------------------------------------
# Trending adds (waiver wire)
# ---------------------------------------------------------------------------


async def get_trending_adds(lookback_hours: int = 24, limit: int = 25) -> list[dict]:
    """
    Return trending waiver wire adds from Sleeper.
    Each item: { player_id, count }
    Cached for 15 minutes.
    """
    key = _REDIS_KEY_TRENDING
    cached = await cache.get(key)
    if cached:
        return cached

    raw: list = await _get(
        f"/players/nfl/trending/add?lookback_hours={lookback_hours}&limit={limit}"
    )
    await cache.set(key, raw, TTL_TRENDING)
    return raw

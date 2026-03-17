"""
Three-tier API key resolution for agent team bootstrap.

Resolution order per provider:
  1. User key      — BYOK; fully isolated rate limits
  2. League key    — shared among league members; only when league.allow_shared_key is True
  3. System key    — platform fallback; restricted to cheapest models only

Usage:
    key, tier = await resolve_api_key(
        user_id=user.id,
        league_id=session.league_id,
        provider="anthropic",
        db=db,
    )
    client = build_llm_client(
        provider=provider,
        api_key=key,
        reasoning_depth="standard" if tier != "system" else "shallow",
    )
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.crypto import decrypt_api_key
from backend.config import settings
from backend.db.models import League, LeagueApiKey, UserApiKey

KeyTier = Literal["user", "league", "system"]

# Models allowed when using the system key — cheapest capable option per provider
SYSTEM_TIER_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}


async def resolve_api_key(
    user_id: uuid.UUID | None,
    league_id: uuid.UUID | None,
    provider: str,
    db: AsyncSession,
) -> tuple[str, KeyTier]:
    """
    Return (plaintext_api_key, tier) for the given user/league/provider.

    user_id may be None for agent-only teams with no associated user account
    (system-managed agents). Tier 1 is skipped in that case.

    Raises ValueError if no key is available at any tier.
    """
    # ── Tier 1: user key ──────────────────────────────────────────────────────
    if user_id is not None:
        user_row = await db.scalar(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == provider,
            )
        )
        if user_row is not None:
            return decrypt_api_key(user_row.encrypted_key), "user"

    # ── Tier 2: league key ────────────────────────────────────────────────────
    if league_id is not None:
        league = await db.scalar(select(League).where(League.id == league_id))
        if league is not None and league.allow_shared_key:
            league_row = await db.scalar(
                select(LeagueApiKey).where(
                    LeagueApiKey.league_id == league_id,
                    LeagueApiKey.provider == provider,
                )
            )
            if league_row is not None:
                return decrypt_api_key(league_row.encrypted_key), "league"

    # ── Tier 3: system key ────────────────────────────────────────────────────
    system_key = _system_key_for(provider)
    if system_key:
        return system_key, "system"

    raise ValueError(
        f"No API key available for provider '{provider}'. "
        "Set a key in Account settings or ask your league manager to configure a league key."
    )


def _system_key_for(provider: str) -> str:
    mapping = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
    }
    return mapping.get(provider, "")


def system_tier_model(provider: str) -> str:
    """Return the model name to enforce when running on the system key."""
    return SYSTEM_TIER_MODELS.get(provider, "claude-haiku-4-5-20251001")

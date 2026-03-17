"""
Factory for building LLM clients from provider config.

Low-level entry point (key already resolved):
    client = build_llm_client(
        provider="anthropic",
        api_key=key,
        reasoning_depth="standard",
    )

High-level entry point (resolves key from DB, enforces system-tier model cap):
    client = await build_llm_client_for_agent(
        user_id=user.id,
        league_id=session.league_id,
        provider="anthropic",
        reasoning_depth="standard",
        db=db,
    )
    # client.tier is "user" | "league" | "system"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.key_resolver import KeyTier, resolve_api_key, system_tier_model
from backend.agents.llm_client import BaseLLMClient
from backend.agents.model_defaults import resolve_model


def build_llm_client(
    provider: str,
    api_key: str,
    reasoning_depth: str = "standard",
    model_override: str | None = None,
) -> BaseLLMClient:
    """
    Build a BaseLLMClient from an already-resolved key.
    Raises ValueError for unknown providers or empty keys.
    """
    if not api_key:
        raise ValueError(f"No API key provided for provider '{provider}'")

    model = resolve_model(provider, reasoning_depth, model_override)

    if provider == "anthropic":
        from backend.agents.llm_providers.anthropic_client import AnthropicClient

        return AnthropicClient(api_key=api_key, model=model)

    if provider == "openai":
        from backend.agents.llm_providers.openai_client import OpenAIClient

        return OpenAIClient(api_key=api_key, model=model)

    if provider == "gemini":
        from backend.agents.llm_providers.gemini_client import GeminiClient

        return GeminiClient(api_key=api_key, model=model)

    raise ValueError(f"Unknown LLM provider: '{provider}'")


@dataclass
class AgentClient:
    """LLM client together with the tier it was sourced from."""

    client: BaseLLMClient
    tier: KeyTier


async def build_llm_client_for_agent(
    user_id: uuid.UUID | None,
    league_id: uuid.UUID | None,
    provider: str,
    reasoning_depth: str = "standard",
    model_override: str | None = None,
    db: AsyncSession = None,  # type: ignore[assignment]
) -> AgentClient:
    """
    Resolve the API key via the three-tier fallback chain, then build the client.

    System-tier calls are capped to the cheapest model regardless of
    reasoning_depth or model_override, to prevent free abuse of platform credits.
    """
    key, tier = await resolve_api_key(user_id, league_id, provider, db)

    # Enforce model cap for system tier
    effective_model = system_tier_model(provider) if tier == "system" else model_override

    client = build_llm_client(
        provider=provider,
        api_key=key,
        reasoning_depth=reasoning_depth,
        model_override=effective_model,
    )
    return AgentClient(client=client, tier=tier)

"""
Factory for building LLM clients from provider config.

Usage (e.g. in EventRunner or session bootstrap):
    client = build_llm_client(
        provider="anthropic",
        api_key=decrypted_user_key or settings.anthropic_api_key,
        reasoning_depth=team_config.get("reasoning_depth", "standard"),
        model_override=team_config.get("model"),
    )
    team = AgentTeam(team_id=..., llm_client=client, ...)
"""

from __future__ import annotations

from backend.agents.llm_client import BaseLLMClient
from backend.agents.model_defaults import resolve_model


def build_llm_client(
    provider: str,
    api_key: str,
    reasoning_depth: str = "standard",
    model_override: str | None = None,
) -> BaseLLMClient:
    """
    Build the right BaseLLMClient for the given provider.

    Raises ValueError for unknown providers or missing API keys.
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

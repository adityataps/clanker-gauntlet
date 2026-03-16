"""
Per-provider model defaults by reasoning depth.

Use claude-haiku / gpt-4o-mini / gemini-flash for routine decisions (cheap + fast).
Use claude-sonnet / gpt-4o / gemini-pro for deep multi-agent reasoning.
"""

from __future__ import annotations

_DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {
        "shallow": "claude-haiku-4-5-20251001",
        "standard": "claude-haiku-4-5-20251001",
        "deep": "claude-sonnet-4-6",
    },
    "openai": {
        "shallow": "gpt-4o-mini",
        "standard": "gpt-4o-mini",
        "deep": "gpt-4o",
    },
    "gemini": {
        "shallow": "gemini-2.0-flash",
        "standard": "gemini-2.0-flash",
        "deep": "gemini-2.5-pro",
    },
}

_FALLBACK = "claude-haiku-4-5-20251001"


def resolve_model(
    provider: str,
    reasoning_depth: str = "standard",
    model_override: str | None = None,
) -> str:
    """Return the model to use. model_override takes precedence if set."""
    if model_override:
        return model_override
    return _DEFAULTS.get(provider, {}).get(reasoning_depth, _FALLBACK)

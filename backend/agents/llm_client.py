"""
Provider-agnostic LLM client interface.

All LLM providers (Anthropic, OpenAI, Gemini) are accessed through BaseLLMClient.
The AgentTeam tool-use loop works entirely with these canonical types and never
imports any provider SDK directly.

Canonical message flow:
    User turn:      Message(role="user",      content=str | [TextBlock | ToolResultBlock])
    Assistant turn: Message(role="assistant",  content=[TextBlock | ToolCallBlock])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Content block types
# ---------------------------------------------------------------------------


@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass
class ToolCallBlock:
    id: str
    name: str
    arguments: dict
    type: Literal["tool_call"] = field(default="tool_call", init=False)


@dataclass
class ToolResultBlock:
    tool_call_id: str
    content: str
    type: Literal["tool_result"] = field(default="tool_result", init=False)


ContentBlock = TextBlock | ToolCallBlock | ToolResultBlock


# ---------------------------------------------------------------------------
# Message and response types
# ---------------------------------------------------------------------------


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    content: list[ContentBlock]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens"]
    usage: TokenUsage


# ---------------------------------------------------------------------------
# Tool definition (canonical — each provider client converts on the way out)
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema object: {"type": "object", "properties": {...}}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseLLMClient(ABC):
    """
    Single-method interface for all LLM providers.

    Implementors translate the canonical Message list and ToolDefinition list
    to their provider's wire format, make the API call, and return a normalized
    LLMResponse. The AgentTeam tool-use loop never touches provider SDKs directly.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str,
        max_tokens: int = 2048,
    ) -> LLMResponse: ...

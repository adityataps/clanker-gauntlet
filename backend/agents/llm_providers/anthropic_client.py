"""Anthropic (Claude) implementation of BaseLLMClient."""

from __future__ import annotations

import anthropic

from backend.agents.llm_client import (
    BaseLLMClient,
    LLMResponse,
    Message,
    TextBlock,
    TokenUsage,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
)

_STOP_REASON_MAP = {
    "tool_use": "tool_use",
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
}


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=_convert_tools(tools),
            messages=[_convert_message(m) for m in messages],
        )

        content: list[TextBlock | ToolCallBlock] = []
        for block in response.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(ToolCallBlock(id=block.id, name=block.name, arguments=block.input))

        return LLMResponse(
            content=content,
            stop_reason=_STOP_REASON_MAP.get(response.stop_reason, "end_turn"),
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )


def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
    ]


def _convert_message(msg: Message) -> dict:
    if isinstance(msg.content, str):
        return {"role": msg.role, "content": msg.content}

    blocks = []
    for block in msg.content:
        if isinstance(block, TextBlock):
            blocks.append({"type": "text", "text": block.text})
        elif isinstance(block, ToolCallBlock):
            blocks.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.arguments}
            )
        elif isinstance(block, ToolResultBlock):
            blocks.append(
                {"type": "tool_result", "tool_use_id": block.tool_call_id, "content": block.content}
            )
    return {"role": msg.role, "content": blocks}

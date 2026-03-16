"""OpenAI (GPT) implementation of BaseLLMClient."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

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
    "tool_calls": "tool_use",
    "stop": "end_turn",
    "length": "max_tokens",
}


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        openai_messages: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            openai_messages.extend(_convert_message(msg))

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            tools=_convert_tools(tools),
            messages=openai_messages,
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        content: list[TextBlock | ToolCallBlock] = []
        if assistant_msg.content:
            content.append(TextBlock(text=assistant_msg.content))
        for tc in assistant_msg.tool_calls or []:
            content.append(
                ToolCallBlock(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
            )

        usage = response.usage
        return LLMResponse(
            content=content,
            stop_reason=_STOP_REASON_MAP.get(choice.finish_reason, "end_turn"),
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            ),
        )


def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _convert_message(msg: Message) -> list[dict]:
    """
    Convert a canonical Message to one or more OpenAI message dicts.

    OpenAI tool results are separate messages with role="tool" rather than
    blocks inside a user message, so one canonical message can expand to many.
    """
    if isinstance(msg.content, str):
        return [{"role": msg.role, "content": msg.content}]

    if msg.role == "user":
        result = []
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                result.append(
                    {"role": "tool", "tool_call_id": block.tool_call_id, "content": block.content}
                )
            elif isinstance(block, TextBlock) and block.text:
                result.append({"role": "user", "content": block.text})
        return result

    # assistant turn — combine text + tool calls into one message
    text_blocks = [b for b in msg.content if isinstance(b, TextBlock)]
    tool_call_blocks = [b for b in msg.content if isinstance(b, ToolCallBlock)]
    out: dict = {
        "role": "assistant",
        "content": text_blocks[0].text if text_blocks else None,
    }
    if tool_call_blocks:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in tool_call_blocks
        ]
    return [out]

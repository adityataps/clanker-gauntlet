"""Google Gemini implementation of BaseLLMClient."""

from __future__ import annotations

import uuid

import google.generativeai as genai

from backend.agents.llm_client import (
    BaseLLMClient,
    ContentBlock,
    LLMResponse,
    Message,
    TextBlock,
    TokenUsage,
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
)


class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        genai.configure(api_key=api_key)
        self._model_name = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        # Build a call_id → function_name map from all prior messages so we can
        # reconstruct FunctionResponse names when we see ToolResultBlock entries.
        # Gemini's FunctionCall proto has no id field — we generate UUIDs for calls
        # in the response parser and embed them as the ToolCallBlock.id.
        call_id_to_name: dict[str, str] = {}
        for msg in messages:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolCallBlock):
                        call_id_to_name[block.id] = block.name

        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system,
            tools=[{"function_declarations": _convert_tools(tools)}],
            generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
        )

        # All messages except the last go into the chat history.
        # The last message is sent via send_message_async.
        history = [_convert_message(m, call_id_to_name) for m in messages[:-1]]
        chat = model.start_chat(history=history)

        last_parts = _message_to_parts(messages[-1], call_id_to_name)
        response = await chat.send_message_async(last_parts)

        content: list[ContentBlock] = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                content.append(TextBlock(text=part.text))
            elif hasattr(part, "function_call") and part.function_call.name:
                content.append(
                    ToolCallBlock(
                        id=str(uuid.uuid4()),
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args),
                    )
                )

        has_tool_calls = any(isinstance(b, ToolCallBlock) for b in content)
        stop_reason: str
        if has_tool_calls:
            stop_reason = "tool_use"
        else:
            finish_reason = response.candidates[0].finish_reason
            # FinishReason.MAX_TOKENS == 2 in the google-generativeai SDK
            stop_reason = "max_tokens" if finish_reason == 2 else "end_turn"

        usage = response.usage_metadata
        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=TokenUsage(
                input_tokens=usage.prompt_token_count,
                output_tokens=usage.candidates_token_count,
            ),
        )


def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
    declarations = []
    for t in tools:
        props = t.parameters.get("properties", {})
        parameters: dict = {
            "type": "object",
            "properties": {
                name: {
                    "type": spec.get("type", "string"),
                    "description": spec.get("description", ""),
                }
                for name, spec in props.items()
            },
        }
        required = t.parameters.get("required")
        if required:
            parameters["required"] = required
        declarations.append(
            {"name": t.name, "description": t.description, "parameters": parameters}
        )
    return declarations


def _message_to_parts(msg: Message, call_id_to_name: dict[str, str]) -> list[dict]:
    if isinstance(msg.content, str):
        return [{"text": msg.content}]
    parts = []
    for block in msg.content:
        if isinstance(block, TextBlock) and block.text:
            parts.append({"text": block.text})
        elif isinstance(block, ToolCallBlock):
            parts.append({"function_call": {"name": block.name, "args": block.arguments}})
        elif isinstance(block, ToolResultBlock):
            fn_name = call_id_to_name.get(block.tool_call_id, "unknown")
            parts.append(
                {"function_response": {"name": fn_name, "response": {"result": block.content}}}
            )
    return parts


def _convert_message(msg: Message, call_id_to_name: dict[str, str]) -> dict:
    role = "model" if msg.role == "assistant" else "user"
    return {"role": role, "parts": _message_to_parts(msg, call_id_to_name)}

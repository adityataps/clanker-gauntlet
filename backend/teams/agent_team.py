"""
AgentTeam — LLM-backed team using the Anthropic SDK tool-use loop.

The agent receives a decision context (roster, projections, news) and uses
Claude in a tool-use loop to reason about the best decision. Tools allow the
agent to explore context data before calling a final submission tool.

Tools are context-scoped: they operate on data already present in the context
object, not on live API calls. This keeps the loop fast and deterministic for
backtesting.

Decision logging:
    After each decision, an optional callback is invoked with the full payload
    and reasoning trace. The EventRunner uses this to persist AgentDecision rows.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

import anthropic

from backend.agents.archetypes import ArchetypeConfig, get_archetype
from backend.teams.context import (
    LineupDecision,
    RosterEntry,
    TradeContext,
    TradeDecision,
    WaiverBid,
    WaiverContext,
    WeekContext,
)
from backend.teams.protocol import BaseTeam

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Max tool-use iterations per decision (safety cap to avoid infinite loops)
MAX_TOOL_ITERATIONS = 12

# Default model — Haiku for cost efficiency on routine decisions
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Fallback reasoning when an agent times out or fails to submit
_TIMEOUT_REASONING = "Decision timed out or failed to parse — fallback applied."


class AgentTeam(BaseTeam):
    """
    LLM-backed team. Uses Claude in a tool-use loop to make decisions.

    Args:
        team_id:           UUID of the DB team record.
        name:              Display name.
        archetype:         Archetype key (e.g. "analytician") or ArchetypeConfig instance.
        api_key:           Anthropic API key for this team.
        model:             Claude model ID (default: Haiku).
        session_id:        Parent session UUID (used in decision log callback).
        on_decision_logged: Optional async callback(session_id, team_id, seq, decision_type,
                            payload, reasoning_trace, tokens_used) called after each decision.
    """

    def __init__(
        self,
        team_id: uuid.UUID,
        name: str,
        archetype: str | ArchetypeConfig,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        session_id: uuid.UUID | None = None,
        on_decision_logged: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(team_id, name)
        self._archetype = get_archetype(archetype) if isinstance(archetype, str) else archetype
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._session_id = session_id
        self._on_decision_logged = on_decision_logged

    # ------------------------------------------------------------------
    # BaseTeam interface
    # ------------------------------------------------------------------

    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision:
        """Run tool-use loop to determine the starting lineup."""
        fallback = LineupDecision(
            starters=_default_starters(ctx.roster),
            reasoning="Auto-lineup: no submission received.",
        )
        decision, trace, tokens = await self._run_loop(
            tools=_lineup_tools(),
            user_message=(
                f"It's Week {ctx.week} of the {ctx.season} NFL season. "
                f"You have ${ctx.faab_balance} FAAB remaining. "
                f"Decide your starting lineup. Use the available tools to research your options, "
                f"then call submit_lineup when ready."
            ),
            submit_tool_name="submit_lineup",
            parse_submission=lambda args: LineupDecision(
                starters=args["starters"],
                reasoning=args.get("reasoning"),
            ),
            tool_handler=lambda name, args: _handle_lineup_tool(name, args, ctx),
            fallback=fallback,
        )
        await self._log_decision("lineup", decision.model_dump(), trace, tokens)
        return decision

    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]:
        """Run tool-use loop to submit FAAB waiver bids."""

        def parse_bids(args: dict) -> list[WaiverBid]:
            return [WaiverBid(**bid) for bid in args.get("bids", [])]

        bids, trace, tokens = await self._run_loop(
            tools=_waiver_tools(),
            user_message=(
                f"It's the waiver period after Week {ctx.week}. "
                f"You have ${ctx.faab_balance} FAAB remaining. "
                f"Review the waiver wire and submit your bids in priority order (1 = top choice). "
                f"You may submit zero bids if you don't want any players. "
                f"Call submit_waiver_bids when done."
            ),
            submit_tool_name="submit_waiver_bids",
            parse_submission=parse_bids,
            tool_handler=lambda name, args: _handle_waiver_tool(name, args, ctx),
            fallback=[],
        )
        await self._log_decision("waiver", [b.model_dump() for b in bids], trace, tokens)
        return bids

    async def evaluate_trade(self, ctx: TradeContext) -> TradeDecision:
        """Run tool-use loop to accept or reject an incoming trade."""
        fallback = TradeDecision(accept=False, reasoning=_TIMEOUT_REASONING)
        decision, trace, tokens = await self._run_loop(
            tools=_trade_tools(),
            user_message=(
                f"You have received a trade proposal in Week {ctx.week}. "
                f"{ctx.proposal.proposing_team_name} offers: "
                f"{ctx.proposal.offered_player_ids} "
                f"in exchange for: {ctx.proposal.requested_player_ids}. "
                f"Note: {ctx.proposal.note or 'None'}. "
                f"Evaluate the trade and call submit_trade_decision when ready."
            ),
            submit_tool_name="submit_trade_decision",
            parse_submission=lambda args: TradeDecision(
                accept=args["accept"],
                reasoning=args.get("reasoning"),
            ),
            tool_handler=lambda name, args: _handle_trade_tool(name, args, ctx),
            fallback=fallback,
        )
        await self._log_decision("trade_response", decision.model_dump(), trace, tokens)
        return decision

    # ------------------------------------------------------------------
    # Generic tool-use loop engine
    # ------------------------------------------------------------------

    async def _run_loop(
        self,
        tools: list[dict],
        user_message: str,
        submit_tool_name: str,
        parse_submission: Callable[[dict], T],
        tool_handler: Callable[[str, dict], str],
        fallback: T,
    ) -> tuple[T, str, int]:
        """
        Run the Claude tool-use loop until the agent calls submit_tool_name.

        Returns (decision, reasoning_trace, total_tokens_used).
        """
        messages: list[dict] = [{"role": "user", "content": user_message}]
        trace_parts: list[str] = []
        total_tokens = 0

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=self._archetype.system_prompt,
                tools=tools,
                messages=messages,
            )
            total_tokens += response.usage.input_tokens + response.usage.output_tokens

            # Collect any text reasoning for the trace
            for block in response.content:
                if block.type == "text" and block.text:
                    trace_parts.append(block.text)

            tool_calls = [b for b in response.content if b.type == "tool_use"]
            submit_call = next((t for t in tool_calls if t.name == submit_tool_name), None)

            if submit_call is not None:
                try:
                    result = parse_submission(submit_call.input)
                    return result, "\n".join(trace_parts), total_tokens
                except Exception as exc:
                    logger.warning(
                        "Failed to parse %s submission from %s: %s",
                        submit_tool_name,
                        self._archetype.name,
                        exc,
                    )
                    return fallback, "\n".join(trace_parts), total_tokens

            # Agent ended turn without calling any tool
            if response.stop_reason == "end_turn" and not tool_calls:
                logger.warning(
                    "%s ended turn without calling %s (iteration %d)",
                    self._archetype.name,
                    submit_tool_name,
                    iteration,
                )
                return fallback, "\n".join(trace_parts), total_tokens

            # Build tool results for non-submit calls and continue loop
            tool_results = []
            for tc in tool_calls:
                if tc.name == submit_tool_name:
                    continue
                content = tool_handler(tc.name, tc.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tc.id, "content": content}
                )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        logger.warning("%s hit max tool iterations (%d)", self._archetype.name, MAX_TOOL_ITERATIONS)
        return fallback, "\n".join(trace_parts), total_tokens

    # ------------------------------------------------------------------
    # Decision logging
    # ------------------------------------------------------------------

    async def _log_decision(
        self,
        decision_type: str,
        payload: Any,
        reasoning_trace: str,
        tokens_used: int,
    ) -> None:
        if self._on_decision_logged is not None:
            try:
                await self._on_decision_logged(
                    session_id=self._session_id,
                    team_id=self.team_id,
                    decision_type=decision_type,
                    payload=payload,
                    reasoning_trace=reasoning_trace,
                    tokens_used=tokens_used,
                )
            except Exception:
                logger.exception("Failed to log decision for team %s", self.team_id)


# ------------------------------------------------------------------
# Tool definitions (returned as dicts for the Anthropic SDK)
# ------------------------------------------------------------------


def _lineup_tools() -> list[dict]:
    return [
        {
            "name": "view_my_roster",
            "description": "View your current roster with player IDs, slots, and acquisition info.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_projections",
            "description": (
                "Get fantasy point projections for players. "
                "Leave player_ids empty to get projections for all your roster players."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "player_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Player IDs to look up. Empty = all roster players.",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "get_recent_news",
            "description": "Get recent injury reports and player news.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max news items to return (default 10).",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "submit_lineup",
            "description": "Submit your final starting lineup. Call this when you've made your decision.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "starters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Player IDs to start this week.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of your lineup choices.",
                    },
                },
                "required": ["starters"],
            },
        },
    ]


def _waiver_tools() -> list[dict]:
    return [
        {
            "name": "view_my_roster",
            "description": "View your current roster.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "view_waiver_wire",
            "description": "View players available on the waiver wire.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "string",
                        "description": "Filter by position (QB, RB, WR, TE, K, DEF). Empty = all.",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "get_projections",
            "description": "Get projections for specific players by ID.",
            "input_schema": {
                "type": "object",
                "properties": {"player_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["player_ids"],
            },
        },
        {
            "name": "get_recent_news",
            "description": "Get recent player news and injury updates.",
            "input_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
        },
        {
            "name": "submit_waiver_bids",
            "description": "Submit your FAAB waiver bids. Priority 1 = top choice.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "bids": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "add_player_id": {"type": "string"},
                                "drop_player_id": {"type": "string"},
                                "bid_amount": {"type": "integer"},
                                "priority": {"type": "integer"},
                            },
                            "required": ["add_player_id", "bid_amount", "priority"],
                        },
                    }
                },
                "required": ["bids"],
            },
        },
    ]


def _trade_tools() -> list[dict]:
    return [
        {
            "name": "view_my_roster",
            "description": "View your current roster.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_projections",
            "description": "Get projections for specific players by ID.",
            "input_schema": {
                "type": "object",
                "properties": {"player_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["player_ids"],
            },
        },
        {
            "name": "submit_trade_decision",
            "description": "Accept or reject the trade proposal.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "accept": {"type": "boolean"},
                    "reasoning": {"type": "string"},
                },
                "required": ["accept"],
            },
        },
    ]


# ------------------------------------------------------------------
# Tool handlers — operate on context data, no external API calls
# ------------------------------------------------------------------


def _handle_lineup_tool(name: str, args: dict, ctx: WeekContext) -> str:
    if name == "view_my_roster":
        return json.dumps([e.model_dump() for e in ctx.roster])
    if name == "get_projections":
        requested = set(args.get("player_ids") or [e.player_id for e in ctx.roster])
        return json.dumps({pid: p for pid, p in ctx.projections.items() if pid in requested})
    if name == "get_recent_news":
        limit = args.get("limit", 10)
        return json.dumps(ctx.recent_news[:limit])
    return json.dumps({"error": f"Unknown tool: {name}"})


def _handle_waiver_tool(name: str, args: dict, ctx: WaiverContext) -> str:
    if name == "view_my_roster":
        return json.dumps([e.model_dump() for e in ctx.roster])
    if name == "view_waiver_wire":
        pos = args.get("position", "").upper()
        wire = ctx.waiver_wire if not pos else [p for p in ctx.waiver_wire if p.position == pos]
        return json.dumps([p.model_dump() for p in wire])
    if name == "get_projections":
        pids = set(args.get("player_ids", []))
        return json.dumps({pid: p for pid, p in ctx.projections.items() if pid in pids})
    if name == "get_recent_news":
        limit = args.get("limit", 10)
        return json.dumps(ctx.recent_news[:limit])
    return json.dumps({"error": f"Unknown tool: {name}"})


def _handle_trade_tool(name: str, args: dict, ctx: TradeContext) -> str:
    if name == "view_my_roster":
        return json.dumps([e.model_dump() for e in ctx.roster])
    if name == "get_projections":
        pids = set(args.get("player_ids", []))
        return json.dumps({pid: p for pid, p in ctx.projections.items() if pid in pids})
    return json.dumps({"error": f"Unknown tool: {name}"})


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _default_starters(roster: list[RosterEntry]) -> list[str]:
    """Return all active-slot players as a fallback lineup."""
    return [e.player_id for e in roster if e.slot == "active"]

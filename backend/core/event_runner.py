"""
EventRunner — the single source of truth for session state transitions.

The runner reads from the season_events table (shared, immutable) and advances
a per-session cursor (current_seq). Teams observe events and submit intentions;
the runner resolves all intentions atomically.

Architecture:
    - One EventRunner instance per active session, managed by EventRunnerService.
    - Maintains a WorldState in memory; serializes to DB at week boundaries.
    - script_speed, compression_factor, and wall_start_time are read from the
      Session DB row — not constructor args.

Script speeds:
    BLITZ       Compressed wall-clock playback; does NOT wait for agents at
                AGENT_WINDOW_OPEN. Events are paced according to compression_factor
                (sim_offset_hours / compression_factor = wall delay). Intermediate
                context events (news, injuries) are pre-loaded via a lookahead
                query so agents see them immediately.

    MANAGED     Same compressed wall-clock pacing as BLITZ. Blocks at each agent
                window until all teams submit (or timeout). Good for league play
                with real humans.

    IMMERSIVE   1:1 wall-clock (compression_factor = 1). No blocking at agent
                windows — deadlines are real timestamps.

Timing:
    Each event's target wall-clock time is:
        wall_time = wall_start_time + timedelta(hours=sim_offset_hours / compression_factor)

    The runner sleeps until wall_time before processing the event. If the runner
    is resuming mid-session (cursor > 0), events whose wall_time is already in
    the past are processed immediately (delay clamped to 0).

Context injection:
    All three modes use the same mechanism under the hood — a shared mutable
    list that ctx.recent_news points to. The difference is in how it's populated:

    BLITZ       Pre-populated via lookahead query before tasks launch.
                Agents see all window events from the start of their loop.

    MANAGED / IMMERSIVE
                Starts empty (or with recent news). The runner appends to the
                list as NEWS_ITEM / INJURY_UPDATE events arrive. Agents pick up
                new items on subsequent tool calls (get_recent_news returns the
                current list contents — not a frozen snapshot).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.world_state import WorldState
from backend.db.models import (
    AgentDecision,
    DecisionType,
    Matchup,
    PlayerScore,
    PriorityReset,
    ProcessedEvent,
    ScriptSpeed,
    SeasonEvent,
    Session,
    SessionStatus,
    Snapshot,
    Standings,
    WaiverBidStatus,
    WaiverMode,
)
from backend.db.models import (
    WaiverBid as WaiverBidRow,
)
from backend.league.waivers import (
    WaiverClaim,
    resolve_faab_auction,
    resolve_priority_claims,
)
from backend.teams.context import (
    RosterEntry,
    TradeContext,
    TradeProposalInfo,
    WaiverContext,
    WeekContext,
)
from backend.teams.context import WaiverBid as WaiverBidModel
from backend.teams.protocol import BaseTeam

logger = logging.getLogger(__name__)

# Batch size for fetching events from DB
_FETCH_BATCH = 200

# Default reaction window timeouts per event type (seconds).
# Overridden per-session via session_config["reaction_timeouts"].
_DEFAULT_REACTION_TIMEOUTS: dict[str, float] = {
    "ROSTER_LOCK": 600.0,  # lineup lock — 10 min for humans to set lineups
    "WAIVER_OPEN": 300.0,  # waiver window — 5 min to submit bids
    "INJURY_UPDATE": 120.0,  # significant injury — 2 min to react
    "WEEK_END": 30.0,  # brief pause after standings update
}

# Types written to processed_events (STAT_UPDATE goes to Redis only)
_AUDITED_EVENT_TYPES = {
    "AGENT_WINDOW_OPEN",
    "AGENT_WINDOW_CLOSE",
    "ROSTER_LOCK",
    "WEEK_END",
    "WAIVER_RESOLVED",
    "TRADE_RESOLVED",
    "INJURY_UPDATE",
    "SEASON_END",
}

# Event types that carry context relevant to agent decisions
_CONTEXT_EVENT_TYPES = {"NEWS_ITEM", "INJURY_UPDATE"}


class EventRunner:
    """
    Cursor-based event loop for a single session.

    Args:
        session_id:   UUID of the session row.
        script_id:    UUID of the season_events script.
        db:           Async DB session.
        teams:        Mapping of team_id -> BaseTeam implementation.
        world_state:  Pre-loaded WorldState (from snapshot or fresh create).
        script_speed: How the runner handles time and agent windows.
                      Read from the Session row by EventRunnerService; can
                      also be passed directly for testing.
        redis:        Optional Redis client for STAT_UPDATE pub/sub.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        script_id: uuid.UUID,
        db: AsyncSession,
        teams: dict[uuid.UUID, BaseTeam],
        world_state: WorldState,
        script_speed: str = ScriptSpeed.BLITZ,
        redis: Any | None = None,
    ) -> None:
        self._session_id = session_id
        self._script_id = script_id
        self._db = db
        self._teams = teams
        self._state = world_state
        self._script_speed = script_speed
        self._waiver_mode: str = WaiverMode.FAAB  # overridden by EventRunnerService
        self._priority_reset: str | None = None  # only relevant for PRIORITY mode
        self._redis = redis

        # Compression timing — set by EventRunnerService from the Session row.
        # compression_factor: sim_hours per wall_hour (e.g. 2856 → 1 h/season).
        # wall_start_time: when the session was first started (UTC).
        # When both are set, the runner sleeps between events to pace delivery.
        # When None (legacy / tests), events fire as fast as possible.
        self._compression_factor: int | None = None
        self._wall_start_time: datetime | None = None

        # Cursor — loaded from DB in run()
        self._current_seq: int = 0

        # Pending agent window state
        self._pending_window_type: str | None = None  # "lineup" | "waiver"
        self._pending_window_seq: int = 0
        self._pending_window_timeout: float = _DEFAULT_REACTION_TIMEOUTS["ROSTER_LOCK"]
        self._pending_tasks: dict[uuid.UUID, asyncio.Task] = {}

        # Reaction window timeouts — overridden by EventRunnerService from session_config
        self._reaction_timeouts: dict[str, float] = {}

        # Shared context feed — mutable list all agent contexts point to.
        # Populated by lookahead (INSTANT) or appended to as events arrive
        # (COMPRESSED / REALTIME). None when no window is open.
        self._window_feed: list[dict] | None = None

        # Monotonic decision sequence counter (per session)
        self._decision_seq: int = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        INSTANT mode: advance until SEASON_END or no more events remain.
        COMPRESSED / REALTIME: same loop; scheduling is handled externally
        by EventRunnerService + APScheduler (Phase 2+).
        Cursor is persisted after every event so sessions survive restarts.
        """
        self._current_seq = await self._load_cursor()
        logger.info(
            "EventRunner starting session=%s speed=%s seq=%d",
            self._session_id,
            self._script_speed,
            self._current_seq,
        )

        while True:
            events = await self._fetch_batch(self._current_seq)
            if not events:
                logger.info(
                    "EventRunner: no more events for session=%s (seq=%d)",
                    self._session_id,
                    self._current_seq,
                )
                break

            for event in events:
                await self._pace_event(event)
                await self._process_event(event)
                self._current_seq = event.seq + 1
                await self._persist_cursor(self._current_seq)

                if event.event_type == "SEASON_END":
                    logger.info("EventRunner: SEASON_END reached for session=%s", self._session_id)
                    return

    # ------------------------------------------------------------------
    # Timing / pacing
    # ------------------------------------------------------------------

    async def _pace_event(self, event: SeasonEvent) -> None:
        """
        Sleep until this event's wall-clock target time before processing.

        wall_time = wall_start_time + timedelta(hours=sim_offset_hours / compression_factor)

        If the target is already in the past (e.g. runner resumed mid-session after
        a pause), the delay is clamped to 0 and the event fires immediately.
        If compression_factor or wall_start_time is not set, this is a no-op.
        """
        if self._compression_factor is None or self._wall_start_time is None:
            return

        from datetime import timedelta

        target = self._wall_start_time + timedelta(
            hours=event.sim_offset_hours / self._compression_factor
        )
        delay = (target - datetime.now(UTC)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    async def _process_event(self, event: SeasonEvent) -> None:
        logger.debug(
            "Processing seq=%d type=%s week=%d",
            event.seq,
            event.event_type,
            event.week_number,
        )

        match event.event_type:
            case "AGENT_WINDOW_OPEN":
                await self._on_agent_window_open(event)
            case "AGENT_WINDOW_CLOSE":
                await self._on_agent_window_close(event)
            case "ROSTER_LOCK":
                pass  # lineup locked by AGENT_WINDOW_CLOSE; audited for UI
            case "GAME_START":
                logger.info("Week %d games starting", event.week_number)
            case "SCORE_UPDATE":
                await self._on_score_update(event)
            case "WEEK_END":
                await self._on_week_end(event)
            case "WAIVER_OPEN":
                pass  # informational; agent window open fires separately
            case "WAIVER_RESOLVED":
                await self._on_waiver_resolved(event)
            case "NEWS_ITEM" | "INJURY_UPDATE":
                await self._on_context_event(event)
            case "TRADE_PROPOSED":
                await self._on_trade_proposed(event)
            case "TRADE_RESOLVED":
                await self._on_trade_resolved(event)
            case "SEASON_END":
                await self._on_season_end(event)
            case _:
                logger.warning("Unknown event type: %s (seq=%d)", event.event_type, event.seq)

        if event.event_type in _AUDITED_EVENT_TYPES:
            await self._audit_event(event)

        await self._route_event(event)

    # ------------------------------------------------------------------
    # Context events (NEWS_ITEM, INJURY_UPDATE)
    # ------------------------------------------------------------------

    async def _on_context_event(self, event: SeasonEvent) -> None:
        """
        For COMPRESSED / REALTIME: append to the live window feed so agents
        see it on their next tool call. For INSTANT: events were already
        pre-loaded via lookahead — this is a no-op.
        """
        if self._script_speed == ScriptSpeed.BLITZ:
            return  # context was pre-loaded at AGENT_WINDOW_OPEN
        if self._window_feed is not None:
            self._window_feed.append(event.payload)

    # ------------------------------------------------------------------
    # AGENT_WINDOW_OPEN
    # ------------------------------------------------------------------

    async def _on_agent_window_open(self, event: SeasonEvent) -> None:
        window_type = event.payload.get("type")  # "lineup" | "waiver"
        week = event.payload.get("week", event.week_number)

        if self._pending_tasks:
            logger.warning(
                "AGENT_WINDOW_OPEN (type=%s) fired while previous window pending — "
                "collecting outstanding tasks first",
                window_type,
            )
            await self._collect_pending_tasks()

        self._pending_window_type = window_type
        self._pending_window_seq = event.seq

        # Resolve timeout from session config, falling back to module defaults
        timeout_key = "ROSTER_LOCK" if window_type == "lineup" else "WAIVER_OPEN"
        self._pending_window_timeout = self._reaction_timeouts.get(
            timeout_key, _DEFAULT_REACTION_TIMEOUTS[timeout_key]
        )

        # Build the shared context feed for this window
        self._window_feed = await self._build_window_feed(event.seq, week)

        # Notify clients that a reaction window is open
        await self._broadcast_reaction_window(
            window_type=window_type,
            week=week,
            triggering_seq=event.seq,
            timeout=self._pending_window_timeout,
            open=True,
        )

        if window_type == "lineup":
            await self._launch_lineup_tasks(week)
        elif window_type == "waiver":
            await self._launch_waiver_tasks(week)
        else:
            logger.warning("Unknown AGENT_WINDOW_OPEN type: %s", window_type)

    async def _build_window_feed(self, open_seq: int, week: int) -> list[dict]:
        """
        Build the initial context feed for the window.

        INSTANT:            Look ahead and pre-load all context events that
                            will arrive before this window closes.
        COMPRESSED/REALTIME: Start with an empty list; events are appended
                             as they arrive during the window.
        """
        if self._script_speed == ScriptSpeed.BLITZ:
            return await self._lookahead_context_events(open_seq, week)
        return []

    async def _lookahead_context_events(self, open_seq: int, week: int) -> list[dict]:
        """
        Query all NEWS_ITEM and INJURY_UPDATE events in the same week that
        come after the current position. Since the script is compiled and
        immutable, this gives agents complete context before they start.
        """
        result = await self._db.execute(
            select(SeasonEvent)
            .where(
                SeasonEvent.script_id == self._script_id,
                SeasonEvent.seq > open_seq,
                SeasonEvent.week_number == week,
                SeasonEvent.event_type.in_(list(_CONTEXT_EVENT_TYPES)),
            )
            .order_by(SeasonEvent.seq)
        )
        events = result.scalars().all()
        logger.debug(
            "Lookahead: pre-loaded %d context events for week %d window",
            len(events),
            week,
        )
        return [e.payload for e in events]

    async def _launch_lineup_tasks(self, week: int) -> None:
        assert self._window_feed is not None
        for team_id, team in self._teams.items():
            ctx = self._build_week_context(team_id, week)
            task = asyncio.create_task(
                team.decide_lineup(ctx),
                name=f"lineup-{team_id}-week{week}",
            )
            self._pending_tasks[team_id] = task
        logger.info("Launched %d lineup tasks for week %d", len(self._pending_tasks), week)

    async def _launch_waiver_tasks(self, week: int) -> None:
        assert self._window_feed is not None
        for team_id, team in self._teams.items():
            ctx = self._build_waiver_context(team_id, week)
            task = asyncio.create_task(
                team.bid_waivers(ctx),
                name=f"waiver-{team_id}-week{week}",
            )
            self._pending_tasks[team_id] = task
        logger.info("Launched %d waiver tasks for week %d", len(self._pending_tasks), week)

    # ------------------------------------------------------------------
    # AGENT_WINDOW_CLOSE (lineup)
    # ------------------------------------------------------------------

    async def _on_agent_window_close(self, event: SeasonEvent) -> None:
        window_type = event.payload.get("type")
        if window_type != "lineup":
            return  # waivers are closed by WAIVER_RESOLVED

        if self._pending_window_type != "lineup":
            logger.warning("AGENT_WINDOW_CLOSE lineup fired but no lineup window was open")
            return

        week = event.payload.get("week", event.week_number)
        triggering_seq = self._pending_window_seq
        results = await self._collect_pending_tasks()

        await self._broadcast_reaction_window(
            window_type="lineup",
            week=week,
            triggering_seq=triggering_seq,
            timeout=self._pending_window_timeout,
            open=False,
        )

        for team_id, result in results.items():
            if result is None:
                logger.warning(
                    "No lineup decision from team %s week %d — using fallback", team_id, week
                )
                continue
            self._state.set_lineup(str(team_id), result.starters)
            await self._persist_agent_decision(
                team_id=team_id,
                decision_type=DecisionType.LINEUP,
                payload=result.model_dump(),
                reasoning_trace=result.reasoning,
                triggered_by=[triggering_seq],
            )

        await self._upsert_matchup_rows(week)
        self._window_feed = None

    # ------------------------------------------------------------------
    # SCORE_UPDATE
    # ------------------------------------------------------------------

    async def _on_score_update(self, event: SeasonEvent) -> None:
        player_id = event.payload.get("player_id")
        pts = float(event.payload.get("pts_half_ppr", 0.0))
        week = event.payload.get("week", event.week_number)

        if not player_id or pts <= 0:
            return

        team_id_str = self._state.add_player_score(player_id, pts)
        if team_id_str is None:
            return  # not a starter

        team_id = uuid.UUID(team_id_str)

        await self._upsert_player_score(
            team_id=team_id,
            player_id=player_id,
            period_number=week,
            pts=pts,
            stats=event.payload.get("stats", {}),
        )
        await self._update_matchup_score(team_id_str, week)

        await self._emit_stat_update(player_id, team_id_str, pts, week)

    # ------------------------------------------------------------------
    # WEEK_END
    # ------------------------------------------------------------------

    async def _on_week_end(self, event: SeasonEvent) -> None:
        week = event.payload.get("week", event.week_number)
        logger.info("Week %d ended for session=%s", week, self._session_id)

        await self._finalize_matchup_winners(week)
        self._state.apply_week_end()
        await self._upsert_standings()

        # Standings-based priority reset (re-ranked after each week)
        if (
            self._waiver_mode == WaiverMode.PRIORITY
            and self._priority_reset == PriorityReset.WEEKLY_STANDINGS
        ):
            self._state.reset_priority_by_standings()

        await self._take_snapshot(seq=event.seq, period_number=week)

        team_ids = [str(tid) for tid in self._teams]
        self._state.generate_matchups(team_ids)

        logger.info(
            "Week %d finalized. Week %d matchups generated.", week, self._state.current_week
        )

    # ------------------------------------------------------------------
    # WAIVER_RESOLVED
    # ------------------------------------------------------------------

    async def _on_waiver_resolved(self, event: SeasonEvent) -> None:
        week = event.payload.get("week", event.week_number)

        if self._pending_window_type != "waiver":
            logger.warning("WAIVER_RESOLVED fired but no waiver window was open")
            return

        triggering_seq = self._pending_window_seq
        results = await self._collect_pending_tasks()

        await self._broadcast_reaction_window(
            window_type="waiver",
            week=week,
            triggering_seq=triggering_seq,
            timeout=self._pending_window_timeout,
            open=False,
        )

        bids_by_team: dict[str, list[WaiverBidModel]] = {
            str(team_id): bids for team_id, bids in results.items() if bids
        }

        if self._waiver_mode == WaiverMode.FAAB:
            claims, updated_balances, winning_team_ids = resolve_faab_auction(
                bids_by_team=bids_by_team,
                faab_balances=self._state.faab_balances,
                waiver_priority=self._state.waiver_priority,
            )
            self._state.faab_balances = updated_balances
        else:
            claims, _, winning_team_ids = resolve_priority_claims(
                bids_by_team=bids_by_team,
                waiver_priority=self._state.waiver_priority,
            )
            if self._priority_reset == PriorityReset.ROLLING:
                self._state.apply_rolling_priority_reset(winning_team_ids)

        for claim in claims:
            if claim.drop_player_id:
                self._state.remove_from_roster(claim.team_id, claim.drop_player_id)
            self._state.add_to_roster(claim.team_id, claim.add_player_id)
            logger.info(
                "Waiver claim: team=%s +%s -%s $%d week=%d",
                claim.team_id,
                claim.add_player_id,
                claim.drop_player_id,
                claim.bid_amount,
                week,
            )

        await self._persist_waiver_results(results, claims, week, triggering_seq=triggering_seq)
        self._window_feed = None

    # ------------------------------------------------------------------
    # TRADE_PROPOSED
    # ------------------------------------------------------------------

    async def _on_trade_proposed(self, event: SeasonEvent) -> None:
        proposal_id = event.payload.get("proposal_id")
        proposing_team_id = uuid.UUID(event.payload["proposing_team_id"])
        receiving_team_id = uuid.UUID(event.payload["receiving_team_id"])

        receiving_team = self._teams.get(receiving_team_id)
        if receiving_team is None:
            logger.warning("Trade proposed to unknown team %s", receiving_team_id)
            return

        proposing_team = self._teams.get(proposing_team_id)

        ctx = TradeContext(
            session_id=self._session_id,
            team_id=receiving_team_id,
            week=event.week_number,
            season=2025,
            sport="nfl",
            roster=self._build_roster_entries(str(receiving_team_id)),
            proposal=TradeProposalInfo(
                proposal_id=uuid.UUID(proposal_id) if proposal_id else uuid.uuid4(),
                proposing_team_id=proposing_team_id,
                proposing_team_name=proposing_team.name if proposing_team else "Unknown",
                offered_player_ids=event.payload.get("offered_player_ids", []),
                requested_player_ids=event.payload.get("requested_player_ids", []),
                note=event.payload.get("note"),
            ),
        )

        try:
            decision = await receiving_team.evaluate_trade(ctx)
        except Exception:
            logger.exception("Trade evaluation failed for team %s", receiving_team_id)
            return

        if decision.accept:
            for pid in ctx.proposal.offered_player_ids:
                self._state.transfer_player(str(proposing_team_id), str(receiving_team_id), pid)
            for pid in ctx.proposal.requested_player_ids:
                self._state.transfer_player(str(receiving_team_id), str(proposing_team_id), pid)

        await self._persist_agent_decision(
            team_id=receiving_team_id,
            decision_type=DecisionType.TRADE_RESPONSE,
            payload=decision.model_dump(),
            reasoning_trace=decision.reasoning,
            triggered_by=[event.seq],
        )

    # ------------------------------------------------------------------
    # TRADE_RESOLVED / SEASON_END
    # ------------------------------------------------------------------

    async def _on_trade_resolved(self, event: SeasonEvent) -> None:
        await self._audit_event(event)

    async def _on_season_end(self, event: SeasonEvent) -> None:
        logger.info("Season ended for session=%s", self._session_id)
        await self._db.execute(
            Session.__table__.update()
            .where(Session.id == self._session_id)
            .values(status=SessionStatus.COMPLETED)
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Task collection — the core of script_speed behavior
    # ------------------------------------------------------------------

    async def _collect_pending_tasks(self) -> dict[uuid.UUID, Any]:
        """
        Await pending agent tasks according to script_speed:

        COMPRESSED   Block until all tasks return (up to _COMPRESSED_TIMEOUT).
                     Every team's decision is applied before the runner advances.

        INSTANT      Take only tasks that are already done (timeout=0).
        REALTIME     Same as INSTANT — deadline was a real timestamp; whatever
                     finished by now gets applied, rest fall back.
        """
        if not self._pending_tasks:
            return {}

        if self._script_speed == ScriptSpeed.MANAGED:
            results = await self._await_all(timeout=self._pending_window_timeout)
        else:
            results = await self._collect_ready()

        self._pending_tasks = {}
        self._pending_window_type = None
        return results

    async def _await_all(self, timeout: float) -> dict[uuid.UUID, Any]:
        """Block until all tasks complete or timeout is reached."""
        results: dict[uuid.UUID, Any] = {}
        for team_id, task in self._pending_tasks.items():
            try:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                results[team_id] = result
            except TimeoutError:
                logger.warning("Team %s timed out after %.0fs — using fallback", team_id, timeout)
                task.cancel()
                results[team_id] = None
            except Exception:
                logger.exception("Task for team %s raised an exception", team_id)
                results[team_id] = None
        return results

    async def _collect_ready(self) -> dict[uuid.UUID, Any]:
        """
        Collect whichever tasks have already completed. Tasks still running
        get cancelled and their team receives a fallback (None).
        Yields control to the event loop once (asyncio.sleep(0)) so that
        any tasks that finished since AGENT_WINDOW_OPEN had a chance to
        complete before we collect.
        """
        await asyncio.sleep(0)
        results: dict[uuid.UUID, Any] = {}
        for team_id, task in self._pending_tasks.items():
            if task.done():
                try:
                    results[team_id] = task.result()
                except Exception:
                    logger.exception("Task for team %s raised an exception", team_id)
                    results[team_id] = None
            else:
                logger.debug("Team %s not done by deadline — using fallback", team_id)
                task.cancel()
                results[team_id] = None
        return results

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def _build_week_context(self, team_id: uuid.UUID, week: int) -> WeekContext:
        # ctx.recent_news points to the shared window feed (mutable list).
        # INSTANT: already pre-populated with lookahead events.
        # COMPRESSED/REALTIME: runner appends to this list as events arrive.
        return WeekContext(
            session_id=self._session_id,
            team_id=team_id,
            week=week,
            season=2025,
            sport="nfl",
            roster=self._build_roster_entries(str(team_id)),
            recent_news=self._window_feed if self._window_feed is not None else [],
            faab_balance=self._state.faab_balance(str(team_id)),
        )

    def _build_waiver_context(self, team_id: uuid.UUID, week: int) -> WaiverContext:
        return WaiverContext(
            session_id=self._session_id,
            team_id=team_id,
            week=week,
            season=2025,
            sport="nfl",
            roster=self._build_roster_entries(str(team_id)),
            recent_news=self._window_feed if self._window_feed is not None else [],
            faab_balance=self._state.faab_balance(str(team_id)),
        )

    def _build_roster_entries(self, team_id: str) -> list[RosterEntry]:
        roster = self._state.rosters.get(team_id, set())
        lineup = self._state.lineups.get(team_id, set())
        return [
            RosterEntry(
                player_id=pid,
                slot="active" if pid in lineup else "bench",
                acquired_week=1,
                acquired_via="waiver",
            )
            for pid in roster
        ]

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _load_cursor(self) -> int:
        result = await self._db.execute(
            select(Session.current_seq).where(Session.id == self._session_id)
        )
        return result.scalar_one_or_none() or 0

    async def _persist_cursor(self, seq: int) -> None:
        await self._db.execute(
            Session.__table__.update().where(Session.id == self._session_id).values(current_seq=seq)
        )
        await self._db.commit()

    async def _fetch_batch(self, from_seq: int) -> list[SeasonEvent]:
        result = await self._db.execute(
            select(SeasonEvent)
            .where(
                SeasonEvent.script_id == self._script_id,
                SeasonEvent.seq >= from_seq,
            )
            .order_by(SeasonEvent.seq)
            .limit(_FETCH_BATCH)
        )
        return list(result.scalars().all())

    async def _audit_event(self, event: SeasonEvent) -> None:
        row = ProcessedEvent(
            session_id=self._session_id,
            seq=event.seq,
            event_type=event.event_type,
            payload=event.payload,
        )
        self._db.add(row)
        await self._db.commit()

    async def _persist_agent_decision(
        self,
        team_id: uuid.UUID,
        decision_type: DecisionType,
        payload: dict,
        reasoning_trace: str | dict | None,
        triggered_by: list[int] | None = None,
        tokens_used: int = 0,
    ) -> None:
        # Normalise reasoning_trace to JSONB — wrap plain strings for forward compatibility
        if isinstance(reasoning_trace, str):
            trace_json: dict | None = {"summary": reasoning_trace, "structured": None}
        else:
            trace_json = reasoning_trace  # already a dict or None

        self._decision_seq += 1
        row = AgentDecision(
            session_id=self._session_id,
            team_id=team_id,
            seq=self._decision_seq,
            decision_type=decision_type,
            payload=payload,
            reasoning_trace=trace_json,
            triggered_by=triggered_by or [],
            tokens_used=tokens_used,
        )
        self._db.add(row)
        await self._db.commit()

    async def _upsert_matchup_rows(self, week: int) -> None:
        for matchup in self._state.current_matchups:
            stmt = (
                pg_insert(Matchup)
                .values(
                    session_id=self._session_id,
                    period_number=week,
                    home_team_id=uuid.UUID(matchup.home_team_id),
                    away_team_id=uuid.UUID(matchup.away_team_id),
                    home_score=matchup.home_score,
                    away_score=matchup.away_score,
                )
                .on_conflict_do_nothing()
            )
            await self._db.execute(stmt)
        await self._db.commit()

    async def _update_matchup_score(self, team_id_str: str, week: int) -> None:
        team_id = uuid.UUID(team_id_str)
        for matchup in self._state.current_matchups:
            if matchup.home_team_id == team_id_str:
                await self._db.execute(
                    Matchup.__table__.update()
                    .where(
                        Matchup.session_id == self._session_id,
                        Matchup.period_number == week,
                        Matchup.home_team_id == team_id,
                    )
                    .values(home_score=matchup.home_score)
                )
                break
            if matchup.away_team_id == team_id_str:
                await self._db.execute(
                    Matchup.__table__.update()
                    .where(
                        Matchup.session_id == self._session_id,
                        Matchup.period_number == week,
                        Matchup.away_team_id == team_id,
                    )
                    .values(away_score=matchup.away_score)
                )
                break
        await self._db.commit()

    async def _upsert_player_score(
        self,
        team_id: uuid.UUID,
        player_id: str,
        period_number: int,
        pts: float,
        stats: dict,
    ) -> None:
        stmt = (
            pg_insert(PlayerScore)
            .values(
                session_id=self._session_id,
                team_id=team_id,
                period_number=period_number,
                player_id=player_id,
                points_total=pts,
                stats_json=stats,
            )
            .on_conflict_do_update(
                index_elements=["session_id", "team_id", "period_number", "player_id"],
                set_={"points_total": pts, "stats_json": stats},
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def _finalize_matchup_winners(self, week: int) -> None:
        for matchup in self._state.current_matchups:
            winner = matchup.winner()
            winner_id = uuid.UUID(winner) if winner else None
            await self._db.execute(
                Matchup.__table__.update()
                .where(
                    Matchup.session_id == self._session_id,
                    Matchup.period_number == week,
                    Matchup.home_team_id == uuid.UUID(matchup.home_team_id),
                )
                .values(
                    home_score=matchup.home_score,
                    away_score=matchup.away_score,
                    winner_team_id=winner_id,
                )
            )
        await self._db.commit()

    async def _upsert_standings(self) -> None:
        for team_id_str in self._state.wins:
            team_id = uuid.UUID(team_id_str)
            stmt = (
                pg_insert(Standings)
                .values(
                    session_id=self._session_id,
                    team_id=team_id,
                    wins=self._state.wins.get(team_id_str, 0),
                    losses=self._state.losses.get(team_id_str, 0),
                    ties=self._state.ties.get(team_id_str, 0),
                    points_for=self._state.points_for.get(team_id_str, 0.0),
                    points_against=self._state.points_against.get(team_id_str, 0.0),
                )
                .on_conflict_do_update(
                    index_elements=["session_id", "team_id"],
                    set_={
                        "wins": self._state.wins.get(team_id_str, 0),
                        "losses": self._state.losses.get(team_id_str, 0),
                        "ties": self._state.ties.get(team_id_str, 0),
                        "points_for": self._state.points_for.get(team_id_str, 0.0),
                        "points_against": self._state.points_against.get(team_id_str, 0.0),
                    },
                )
            )
            await self._db.execute(stmt)
        await self._db.commit()

    async def _take_snapshot(self, seq: int, period_number: int) -> None:
        snapshot = Snapshot(
            session_id=self._session_id,
            seq=seq,
            period_number=period_number,
            world_state=self._state.to_snapshot(),
        )
        self._db.add(snapshot)
        await self._db.commit()

    async def _persist_waiver_results(
        self,
        bids_by_team: dict[uuid.UUID, list[WaiverBidModel] | None],
        claims: list[WaiverClaim],
        week: int,
        *,
        triggering_seq: int = 0,
    ) -> None:
        winning_teams: dict[str, str] = {c.add_player_id: c.team_id for c in claims}
        claimed: set[str] = set(winning_teams.keys())

        for team_id, bids in bids_by_team.items():
            if not bids:
                continue
            team_id_str = str(team_id)
            for bid in bids:
                won = (
                    bid.add_player_id in claimed
                    and winning_teams.get(bid.add_player_id) == team_id_str
                )
                self._db.add(
                    WaiverBidRow(
                        session_id=self._session_id,
                        team_id=team_id,
                        period_number=week,
                        add_player_id=bid.add_player_id,
                        drop_player_id=bid.drop_player_id,
                        bid_amount=bid.bid_amount,
                        priority=bid.priority,
                        status=WaiverBidStatus.WON if won else WaiverBidStatus.LOST,
                        processed_at=datetime.now(UTC),
                    )
                )

        await self._db.commit()

        for team_id, bids in bids_by_team.items():
            if bids is not None:
                await self._persist_agent_decision(
                    team_id=team_id,
                    decision_type=DecisionType.WAIVER,
                    payload={"bids": [b.model_dump() for b in bids]},
                    reasoning_trace=None,
                    triggered_by=[triggering_seq] if triggering_seq else [],
                )

    async def _emit_stat_update(self, player_id: str, team_id: str, pts: float, week: int) -> None:
        """Publish a STAT_UPDATE to the broadcast stream. Not stored in DB."""
        if self._redis is None:
            return
        try:
            await self._redis.xadd(
                f"session:{self._session_id}:broadcast",
                {
                    "event_type": "STAT_UPDATE",
                    "seq": "0",
                    "payload": json.dumps(
                        {"player_id": player_id, "team_id": team_id, "pts": pts, "week": week}
                    ),
                },
            )
        except Exception:
            logger.exception("Failed to emit STAT_UPDATE to Redis")

    async def _route_event(
        self,
        event: SeasonEvent,
        *,
        team_recipients: list[uuid.UUID] | None = None,
    ) -> None:
        """
        Route a processed event to Redis streams for WebSocket delivery.

        All events go to session:{id}:broadcast (the shared event log).
        If team_recipients is set, the event is ALSO sent to each team's
        session:{id}:team:{team_id} stream so the UI can show team-specific
        action prompts.
        """
        if self._redis is None:
            return
        fields = {
            "event_type": event.event_type,
            "seq": str(event.seq),
            "payload": json.dumps(event.payload or {}),
        }
        try:
            await self._redis.xadd(f"session:{self._session_id}:broadcast", fields)
            if team_recipients:
                for tid in team_recipients:
                    await self._redis.xadd(f"session:{self._session_id}:team:{tid}", fields)
        except Exception:
            logger.exception("Failed to route event %s (seq=%d)", event.event_type, event.seq)

    async def _broadcast_reaction_window(
        self,
        *,
        window_type: str,
        week: int,
        triggering_seq: int,
        timeout: float,
        open: bool,
    ) -> None:
        """
        Publish a REACTION_WINDOW_OPEN or REACTION_WINDOW_CLOSE notification
        to the broadcast stream so clients can show/hide deadline countdowns.
        """
        if self._redis is None:
            return
        event_type = "REACTION_WINDOW_OPEN" if open else "REACTION_WINDOW_CLOSE"
        try:
            await self._redis.xadd(
                f"session:{self._session_id}:broadcast",
                {
                    "event_type": event_type,
                    "seq": "0",
                    "payload": json.dumps(
                        {
                            "window_type": window_type,
                            "week": week,
                            "triggering_seq": triggering_seq,
                            "timeout_seconds": timeout,
                        }
                    ),
                },
            )
        except Exception:
            logger.exception("Failed to broadcast %s", event_type)

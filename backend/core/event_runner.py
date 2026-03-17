"""
EventRunner — the single source of truth for session state transitions.

The runner reads from the season_events table (shared, immutable) and advances
a per-session cursor (current_seq). Teams observe events and submit intentions;
the runner resolves all intentions atomically.

Architecture:
    - One EventRunner instance per active session, managed by EventRunnerService.
    - Maintains a WorldState in memory; serializes to DB at week boundaries.
    - script_speed is read from the Session DB row — not a constructor arg.

Script speeds:
    INSTANT     Tight async loop, no waiting for agents. All intermediate
                context events (news, injuries) are pre-loaded via a lookahead
                query at AGENT_WINDOW_OPEN (script is immutable, so we know
                what's coming before agents start reasoning).

    COMPRESSED  Compressed wall-clock advancement (APScheduler — Phase 2+).
                Blocks at each agent window: AGENT_WINDOW_CLOSE / WAIVER_RESOLVED
                waits for all teams to submit before the runner advances.
                Good for league-with-friends play without a 17-week commitment.

    REALTIME    1:1 wall-clock. No blocking at agent windows — deadlines are
                real timestamps. Uses a live feed: intermediate events are
                appended to a shared list that agent tool calls read dynamically.

Context injection:
    All three modes use the same mechanism under the hood — a shared mutable
    list that ctx.recent_news points to. The difference is in how it's populated:

    INSTANT     Pre-populated via lookahead query before tasks launch.
                Agents see all window events from the start of their loop.

    COMPRESSED  / REALTIME
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

# Safety timeout for COMPRESSED mode (agents should finish well before this)
_COMPRESSED_TIMEOUT = 300.0  # 5 minutes

# Types written to processed_events (STAT_UPDATE goes to Redis only)
_AUDITED_EVENT_TYPES = {
    "AGENT_WINDOW_OPEN",
    "AGENT_WINDOW_CLOSE",
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

        # Cursor — loaded from DB in run()
        self._current_seq: int = 0

        # Pending agent window state
        self._pending_window_type: str | None = None  # "lineup" | "waiver"
        self._pending_window_seq: int = 0
        self._pending_tasks: dict[uuid.UUID, asyncio.Task] = {}

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
                await self._process_event(event)
                self._current_seq = event.seq + 1
                await self._persist_cursor(self._current_seq)

                if event.event_type == "SEASON_END":
                    logger.info("EventRunner: SEASON_END reached for session=%s", self._session_id)
                    return

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
                pass  # lineup already locked by AGENT_WINDOW_CLOSE
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

        await self._broadcast_event(event)

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

        # Build the shared context feed for this window
        self._window_feed = await self._build_window_feed(event.seq, week)

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
        results = await self._collect_pending_tasks()

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

        results = await self._collect_pending_tasks()

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

        await self._persist_waiver_results(results, claims, week)
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
            results = await self._await_all(timeout=_COMPRESSED_TIMEOUT)
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
        reasoning_trace: str | None,
        tokens_used: int = 0,
    ) -> None:
        self._decision_seq += 1
        row = AgentDecision(
            session_id=self._session_id,
            team_id=team_id,
            seq=self._decision_seq,
            decision_type=decision_type,
            payload=payload,
            reasoning_trace=reasoning_trace,
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
                )

    async def _emit_stat_update(self, player_id: str, team_id: str, pts: float, week: int) -> None:
        """Publish a STAT_UPDATE to the Redis stream. Not stored in DB."""
        if self._redis is None:
            return
        try:
            await self._redis.xadd(
                f"session:{self._session_id}:events",
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

    async def _broadcast_event(self, event: SeasonEvent) -> None:
        """Publish any processed season event to the Redis stream for WebSocket delivery."""
        if self._redis is None:
            return
        try:
            await self._redis.xadd(
                f"session:{self._session_id}:events",
                {
                    "event_type": event.event_type,
                    "seq": str(event.seq),
                    "payload": json.dumps(event.payload or {}),
                },
            )
        except Exception:
            logger.exception(
                "Failed to broadcast event type=%s seq=%d", event.event_type, event.seq
            )

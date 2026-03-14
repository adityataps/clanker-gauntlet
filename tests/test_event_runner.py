"""
Tests for EventRunner — uses AsyncMock for DB and stub teams.

These are unit/integration tests that verify the runner's event dispatch,
AGENT_WINDOW lifecycle, FAAB resolution, scoring, and snapshot logic
without requiring a real PostgreSQL connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.event_runner import EventRunner
from backend.core.world_state import MatchupState, WorldState
from backend.db.models import ScriptSpeed, SeasonEvent
from backend.teams.context import LineupDecision, WaiverBid, WaiverContext, WeekContext
from backend.teams.protocol import BaseTeam

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_event(
    seq: int,
    event_type: str,
    payload: dict,
    week: int = 1,
    offset: float = 0.0,
) -> SeasonEvent:
    e = MagicMock(spec=SeasonEvent)
    e.seq = seq
    e.event_type = event_type
    e.payload = payload
    e.week_number = week
    e.sim_offset_hours = offset
    return e


class StubTeam(BaseTeam):
    """Configurable stub that returns preset decisions."""

    def __init__(self, team_id: uuid.UUID, name: str = "Stub") -> None:
        super().__init__(team_id, name)
        self.lineup_response: LineupDecision = LineupDecision(starters=[], reasoning="stub")
        self.waiver_response: list[WaiverBid] = []
        self.decide_lineup_calls: int = 0
        self.bid_waivers_calls: int = 0

    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision:
        self.decide_lineup_calls += 1
        return self.lineup_response

    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]:
        self.bid_waivers_calls += 1
        return self.waiver_response

    async def evaluate_trade(self, ctx):
        from backend.teams.context import TradeDecision

        return TradeDecision(accept=False)


def make_runner(
    teams: dict[uuid.UUID, StubTeam] | None = None,
    world_state: WorldState | None = None,
    script_speed: str = ScriptSpeed.MANAGED,
) -> tuple[EventRunner, AsyncMock]:
    """Build an EventRunner with mocked DB and optional teams/world_state."""
    session_id = uuid.uuid4()
    script_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=0),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )
    )
    db.commit = AsyncMock()
    db.add = MagicMock()

    if teams is None:
        t1 = uuid.uuid4()
        teams = {t1: StubTeam(t1)}

    if world_state is None:
        world_state = WorldState.create(session_id, list(teams.keys()))

    runner = EventRunner(
        session_id=session_id,
        script_id=script_id,
        db=db,
        teams=teams,
        world_state=world_state,
        script_speed=script_speed,
    )
    return runner, db


# ---------------------------------------------------------------------------
# _process_event dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_game_start_does_not_raise():
    runner, _ = make_runner()
    event = make_event(1, "GAME_START", {"week": 1})
    await runner._process_event(event)


@pytest.mark.asyncio
async def test_waiver_open_does_not_raise():
    runner, _ = make_runner()
    event = make_event(2, "WAIVER_OPEN", {"week": 1})
    await runner._process_event(event)


@pytest.mark.asyncio
async def test_news_item_does_not_raise():
    runner, _ = make_runner()
    event = make_event(3, "NEWS_ITEM", {"text": "Player is healthy"})
    await runner._process_event(event)


@pytest.mark.asyncio
async def test_unknown_event_type_logs_warning_does_not_raise():
    runner, _ = make_runner()
    event = make_event(99, "FUTURE_EVENT_TYPE", {})
    await runner._process_event(event)


# ---------------------------------------------------------------------------
# AGENT_WINDOW_OPEN (lineup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lineup_window_open_launches_tasks_for_all_teams():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    team1, team2 = StubTeam(t1, "T1"), StubTeam(t2, "T2")
    runner, _ = make_runner(teams={t1: team1, t2: team2})

    event = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(event)

    assert len(runner._pending_tasks) == 2
    assert runner._pending_window_type == "lineup"

    # Clean up tasks
    for task in runner._pending_tasks.values():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@pytest.mark.asyncio
async def test_waiver_window_open_launches_tasks_for_all_teams():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    runner, _ = make_runner(teams={t1: StubTeam(t1), t2: StubTeam(t2)})

    event = make_event(1, "AGENT_WINDOW_OPEN", {"type": "waiver", "week": 1})
    await runner._process_event(event)

    assert len(runner._pending_tasks) == 2
    assert runner._pending_window_type == "waiver"

    for task in runner._pending_tasks.values():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


# ---------------------------------------------------------------------------
# AGENT_WINDOW_CLOSE (lineup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lineup_close_applies_lineup_to_world_state():
    t1 = uuid.uuid4()
    team1 = StubTeam(t1)
    state = WorldState.create(uuid.uuid4(), [t1])
    # Add players to roster so set_lineup can validate them
    state.add_to_roster(str(t1), "p1")
    state.add_to_roster(str(t1), "p2")
    team1.lineup_response = LineupDecision(starters=["p1", "p2"])

    runner, _ = make_runner(teams={t1: team1}, world_state=state)

    # Open the window
    open_event = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_event)

    # Wait briefly for tasks to complete (they're instant stubs)
    await asyncio.sleep(0)

    # Close the window
    close_event = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    await runner._process_event(close_event)

    assert state.lineups.get(str(t1)) == {"p1", "p2"}


@pytest.mark.asyncio
async def test_lineup_close_clears_pending_tasks():
    t1 = uuid.uuid4()
    runner, _ = make_runner(teams={t1: StubTeam(t1)})

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)
    assert runner._pending_tasks

    close_ev = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    await runner._process_event(close_ev)
    assert runner._pending_tasks == {}
    assert runner._pending_window_type is None


# ---------------------------------------------------------------------------
# SCORE_UPDATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_update_credits_starting_player():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1, t2])
    state.current_matchups = [MatchupState(home_team_id=str(t1), away_team_id=str(t2))]
    state.add_to_roster(str(t1), "p1")
    state.set_lineup(str(t1), ["p1"])

    runner, _ = make_runner(teams={t1: StubTeam(t1), t2: StubTeam(t2)}, world_state=state)

    event = make_event(5, "SCORE_UPDATE", {"player_id": "p1", "pts_half_ppr": 22.5, "week": 1})
    await runner._process_event(event)

    assert state.current_matchups[0].home_score == pytest.approx(22.5)


@pytest.mark.asyncio
async def test_score_update_ignores_benched_player():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1, t2])
    state.current_matchups = [MatchupState(home_team_id=str(t1), away_team_id=str(t2))]
    state.add_to_roster(str(t1), "p1")
    # p1 is on roster but NOT in lineup

    runner, _ = make_runner(teams={t1: StubTeam(t1), t2: StubTeam(t2)}, world_state=state)

    event = make_event(5, "SCORE_UPDATE", {"player_id": "p1", "pts_half_ppr": 22.5, "week": 1})
    await runner._process_event(event)

    assert state.current_matchups[0].home_score == 0.0


@pytest.mark.asyncio
async def test_score_update_ignores_free_agent():
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    runner, _ = make_runner(teams={t1: StubTeam(t1)}, world_state=state)

    event = make_event(
        5, "SCORE_UPDATE", {"player_id": "free_agent", "pts_half_ppr": 10.0, "week": 1}
    )
    await runner._process_event(event)

    for m in state.current_matchups:
        assert m.home_score == 0.0
        assert m.away_score == 0.0


# ---------------------------------------------------------------------------
# WEEK_END
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_week_end_advances_week():
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    assert state.current_week == 1
    runner, _ = make_runner(teams={t1: StubTeam(t1)}, world_state=state)

    event = make_event(10, "WEEK_END", {"week": 1})
    await runner._process_event(event)

    assert state.current_week == 2


@pytest.mark.asyncio
async def test_week_end_updates_standings():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1, t2])
    state.current_matchups = [
        MatchupState(home_team_id=str(t1), away_team_id=str(t2), home_score=100.0, away_score=50.0)
    ]
    runner, _ = make_runner(teams={t1: StubTeam(t1), t2: StubTeam(t2)}, world_state=state)

    event = make_event(10, "WEEK_END", {"week": 1})
    await runner._process_event(event)

    assert state.wins.get(str(t1), 0) == 1
    assert state.losses.get(str(t2), 0) == 1


# ---------------------------------------------------------------------------
# WAIVER_RESOLVED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_waiver_resolved_applies_roster_changes():
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])

    team1 = StubTeam(t1)
    team1.waiver_response = [WaiverBid(add_player_id="new_player", bid_amount=20, priority=1)]

    runner, _ = make_runner(teams={t1: team1}, world_state=state)

    # Open waiver window
    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "waiver", "week": 1})
    await runner._process_event(open_ev)

    await asyncio.sleep(0)  # let tasks complete

    # Resolve
    resolved_ev = make_event(2, "WAIVER_RESOLVED", {"week": 1})
    await runner._process_event(resolved_ev)

    assert "new_player" in state.rosters.get(str(t1), set())
    assert state.faab_balances[str(t1)] == 80  # 100 - 20


@pytest.mark.asyncio
async def test_waiver_resolved_applies_drop():
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    state.add_to_roster(str(t1), "old_player")

    team1 = StubTeam(t1)
    team1.waiver_response = [
        WaiverBid(
            add_player_id="new_player", drop_player_id="old_player", bid_amount=10, priority=1
        )
    ]
    runner, _ = make_runner(teams={t1: team1}, world_state=state)

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "waiver", "week": 1})
    await runner._process_event(open_ev)
    await asyncio.sleep(0)

    resolved_ev = make_event(2, "WAIVER_RESOLVED", {"week": 1})
    await runner._process_event(resolved_ev)

    assert "new_player" in state.rosters.get(str(t1), set())
    assert "old_player" not in state.rosters.get(str(t1), set())


# ---------------------------------------------------------------------------
# SEASON_END
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_end_does_not_raise():
    runner, _ = make_runner()
    event = make_event(999, "SEASON_END", {"season": 2025})
    await runner._process_event(event)


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_persists_cursor_after_each_event():
    """EventRunner.run() should call persist_cursor after every event."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    runner, db = make_runner(teams={t1: StubTeam(t1)}, world_state=state)

    events = [
        make_event(1, "GAME_START", {"week": 1}),
        make_event(2, "NEWS_ITEM", {"text": "test"}),
        make_event(3, "SEASON_END", {"season": 2025}),
    ]

    # Patch _fetch_batch to return our events once, then empty
    call_count = 0

    async def fake_fetch(from_seq: int) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [e for e in events if e.seq >= from_seq]
        return []

    runner._fetch_batch = fake_fetch

    # Patch _load_cursor to return 0
    async def fake_load_cursor():
        return 0

    runner._load_cursor = fake_load_cursor

    await runner.run()

    # execute was called (cursor updates go through db.execute)
    assert db.execute.called


# ---------------------------------------------------------------------------
# Script speed — COMPRESSED blocks, INSTANT/REALTIME don't wait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compressed_waits_for_agents():
    """COMPRESSED mode: runner blocks at CLOSE until agent task is done."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    state.add_to_roster(str(t1), "p1")
    completed = []

    class SlowTeam(StubTeam):
        async def decide_lineup(self, ctx):
            await asyncio.sleep(0.05)  # simulate real work
            completed.append("done")
            return LineupDecision(starters=["p1"])

    runner, _ = make_runner(
        teams={t1: SlowTeam(t1)},
        world_state=state,
        script_speed=ScriptSpeed.MANAGED,
    )

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)

    close_ev = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    await runner._process_event(close_ev)

    # In COMPRESSED mode the runner waited — decision must be recorded
    assert completed == ["done"]
    assert state.lineups.get(str(t1)) == {"p1"}


@pytest.mark.asyncio
async def test_instant_does_not_wait_for_slow_agents():
    """INSTANT mode: runner collects only completed tasks, uses fallback for slow ones."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    state.add_to_roster(str(t1), "p1")

    class SlowTeam(StubTeam):
        async def decide_lineup(self, ctx):
            await asyncio.sleep(10)  # never completes in time
            return LineupDecision(starters=["p1"])

    runner, _ = make_runner(
        teams={t1: SlowTeam(t1)},
        world_state=state,
        script_speed=ScriptSpeed.BLITZ,
    )

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)

    close_ev = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    await runner._process_event(close_ev)

    # Slow agent got fallback (None result) — no lineup set (set_lineup skipped for None)
    assert str(t1) not in state.lineups or state.lineups.get(str(t1)) == set()


@pytest.mark.asyncio
async def test_realtime_does_not_wait_for_slow_agents():
    """REALTIME mode behaves the same as INSTANT for task collection."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])

    class SlowTeam(StubTeam):
        async def decide_lineup(self, ctx):
            await asyncio.sleep(10)
            return LineupDecision(starters=[])

    runner, _ = make_runner(
        teams={t1: SlowTeam(t1)},
        world_state=state,
        script_speed=ScriptSpeed.IMMERSIVE,
    )

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)

    close_ev = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    # Should return quickly (not block on the slow agent)
    await runner._process_event(close_ev)


# ---------------------------------------------------------------------------
# Context injection — live feed (COMPRESSED/REALTIME)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_feed_populated_by_intermediate_events():
    """NEWS_ITEM events arriving after AGENT_WINDOW_OPEN are appended to the shared feed."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    runner, _ = make_runner(
        teams={t1: StubTeam(t1)},
        world_state=state,
        script_speed=ScriptSpeed.MANAGED,
    )

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)

    assert runner._window_feed == []  # starts empty in COMPRESSED mode

    news_ev = make_event(2, "NEWS_ITEM", {"text": "Star RB questionable", "week": 1})
    await runner._process_event(news_ev)

    assert len(runner._window_feed) == 1
    assert runner._window_feed[0]["text"] == "Star RB questionable"

    # Cleanup
    for task in runner._pending_tasks.values():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@pytest.mark.asyncio
async def test_instant_mode_does_not_append_to_feed_during_window():
    """INSTANT: news events mid-window are ignored (context was pre-loaded at OPEN)."""
    t1 = uuid.uuid4()
    runner, _ = make_runner(
        teams={t1: StubTeam(t1)},
        script_speed=ScriptSpeed.BLITZ,
    )

    # Manually set _window_feed (bypassing lookahead DB call) to simulate open window
    runner._window_feed = ["pre_loaded_item"]
    runner._pending_window_type = "lineup"

    news_ev = make_event(2, "NEWS_ITEM", {"text": "breaking news"})
    await runner._process_event(news_ev)

    # Should NOT have been appended
    assert runner._window_feed == ["pre_loaded_item"]


@pytest.mark.asyncio
async def test_window_feed_cleared_after_close():
    """_window_feed is set to None after AGENT_WINDOW_CLOSE."""
    t1 = uuid.uuid4()
    state = WorldState.create(uuid.uuid4(), [t1])
    runner, _ = make_runner(
        teams={t1: StubTeam(t1)},
        world_state=state,
        script_speed=ScriptSpeed.MANAGED,
    )

    open_ev = make_event(1, "AGENT_WINDOW_OPEN", {"type": "lineup", "week": 1})
    await runner._process_event(open_ev)
    assert runner._window_feed is not None

    close_ev = make_event(2, "AGENT_WINDOW_CLOSE", {"type": "lineup", "week": 1})
    await runner._process_event(close_ev)
    assert runner._window_feed is None


# ---------------------------------------------------------------------------
# EventRunnerService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_service_start_and_is_running():
    from backend.core.runner_service import EventRunnerService

    t1 = uuid.uuid4()
    session_id = uuid.uuid4()
    script_id = uuid.uuid4()

    # Build a mock DB that returns a valid Session row and no snapshot
    mock_session_row = MagicMock()
    mock_session_row.id = session_id
    mock_session_row.script_id = script_id
    mock_session_row.script_speed = ScriptSpeed.BLITZ
    mock_session_row.status = "in_progress"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_session_row)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )
    )
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    class MockSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *_):
            pass

    service = EventRunnerService(db_session_factory=MockSessionFactory())

    team = StubTeam(t1)
    await service.start(session_id, teams={t1: team})

    assert service.is_running(session_id)

    await service.pause(session_id)
    assert not service.is_running(session_id)


@pytest.mark.asyncio
async def test_runner_service_start_is_idempotent():
    from backend.core.runner_service import EventRunnerService

    session_id = uuid.uuid4()

    # Service with a DB that returns nothing (session not found → task ends immediately)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    class MockFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *_):
            pass

    service = EventRunnerService(db_session_factory=MockFactory())

    t1 = uuid.uuid4()
    await service.start(session_id, {t1: StubTeam(t1)})
    first_task = service._tasks.get(session_id)

    # Calling start again while running should be a no-op
    await service.start(session_id, {t1: StubTeam(t1)})
    assert service._tasks.get(session_id) is first_task


# ---------------------------------------------------------------------------
# Archetype system
# ---------------------------------------------------------------------------


def test_get_archetype_valid_keys():
    from backend.agents.archetypes import ARCHETYPES, get_archetype

    for key in ARCHETYPES:
        archetype = get_archetype(key)
        assert archetype.name
        assert archetype.system_prompt


def test_get_archetype_invalid_key_raises():
    from backend.agents.archetypes import get_archetype

    with pytest.raises(ValueError, match="Unknown archetype"):
        get_archetype("nonexistent_archetype")

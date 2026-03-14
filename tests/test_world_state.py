"""
Tests for WorldState — pure unit tests, no DB required.
"""

import uuid

from backend.core.world_state import MatchupState, WorldState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_team_ids(n: int = 4) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def make_state(n_teams: int = 4, faab: int = 100) -> tuple[WorldState, list[str]]:
    team_uuids = make_team_ids(n_teams)
    state = WorldState.create(uuid.uuid4(), team_uuids, initial_faab=faab)
    str_ids = [str(tid) for tid in team_uuids]
    return state, str_ids


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


def test_create_initializes_all_teams():
    state, str_ids = make_state(4)
    assert set(state.rosters.keys()) == set(str_ids)
    assert set(state.faab_balances.keys()) == set(str_ids)
    assert all(bal == 100 for bal in state.faab_balances.values())


def test_create_starts_with_empty_rosters():
    state, _ = make_state(4)
    for roster in state.rosters.values():
        assert len(roster) == 0


def test_create_generates_matchups_for_even_teams():
    state, str_ids = make_state(4)
    assert len(state.current_matchups) == 2
    all_teams_in_matchups = set()
    for m in state.current_matchups:
        all_teams_in_matchups.add(m.home_team_id)
        all_teams_in_matchups.add(m.away_team_id)
    assert all_teams_in_matchups == set(str_ids)


def test_create_odd_teams_one_bye():
    state, str_ids = make_state(3)
    # 3 teams → 1 matchup, 1 team on bye
    assert len(state.current_matchups) == 1


# ---------------------------------------------------------------------------
# Roster management
# ---------------------------------------------------------------------------


def test_add_and_remove_from_roster():
    state, (t1, *_) = make_state()
    state.add_to_roster(t1, "p1")
    assert "p1" in state.rosters[t1]
    state.remove_from_roster(t1, "p1")
    assert "p1" not in state.rosters[t1]


def test_remove_from_roster_also_clears_lineup():
    state, (t1, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.set_lineup(t1, ["p1"])
    assert state.is_starter(t1, "p1")
    state.remove_from_roster(t1, "p1")
    assert not state.is_starter(t1, "p1")


def test_transfer_player_moves_between_teams():
    state, (t1, t2, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.transfer_player(t1, t2, "p1")
    assert "p1" not in state.rosters[t1]
    assert "p1" in state.rosters[t2]


def test_player_team_returns_correct_owner():
    state, (t1, t2, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.add_to_roster(t2, "p2")
    assert state.player_team("p1") == t1
    assert state.player_team("p2") == t2
    assert state.player_team("p_unknown") is None


# ---------------------------------------------------------------------------
# Lineup management
# ---------------------------------------------------------------------------


def test_set_lineup_only_includes_rostered_players():
    state, (t1, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.add_to_roster(t1, "p2")
    # p3 is NOT on the roster — should be silently excluded
    state.set_lineup(t1, ["p1", "p2", "p3"])
    assert state.lineups[t1] == {"p1", "p2"}


def test_is_starter():
    state, (t1, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.set_lineup(t1, ["p1"])
    assert state.is_starter(t1, "p1")
    assert not state.is_starter(t1, "p2")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_add_player_score_credits_starter():
    state, (t1, t2, *_) = make_state()
    # Ensure t1 and t2 are in the same matchup
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    state.add_to_roster(t1, "p1")
    state.set_lineup(t1, ["p1"])
    result = state.add_player_score("p1", 20.0)
    assert result == t1
    assert state.current_matchups[0].home_score == 20.0
    assert state.current_matchups[0].away_score == 0.0


def test_add_player_score_ignores_bench_player():
    state, (t1, t2, *_) = make_state()
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    state.add_to_roster(t1, "p1")
    # p1 on roster but NOT in lineup (benched)
    result = state.add_player_score("p1", 20.0)
    assert result is None
    assert state.current_matchups[0].home_score == 0.0


def test_add_player_score_ignores_unowned_player():
    state, (t1, t2, *_) = make_state()
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    result = state.add_player_score("p_free_agent", 30.0)
    assert result is None


def test_away_team_score_credited_correctly():
    state, (t1, t2, *_) = make_state()
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    state.add_to_roster(t2, "p2")
    state.set_lineup(t2, ["p2"])
    state.add_player_score("p2", 15.5)
    assert state.current_matchups[0].away_score == 15.5


# ---------------------------------------------------------------------------
# FAAB
# ---------------------------------------------------------------------------


def test_deduct_faab():
    state, (t1, *_) = make_state(faab=100)
    state.deduct_faab(t1, 30)
    assert state.faab_balance(t1) == 70


def test_deduct_faab_floors_at_zero():
    state, (t1, *_) = make_state(faab=10)
    state.deduct_faab(t1, 50)
    assert state.faab_balance(t1) == 0


# ---------------------------------------------------------------------------
# apply_week_end
# ---------------------------------------------------------------------------


def test_apply_week_end_updates_standings_winner():
    state, (t1, t2, *_) = make_state()
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    state.add_to_roster(t1, "p1")
    state.set_lineup(t1, ["p1"])
    state.add_player_score("p1", 100.0)

    state.apply_week_end()

    assert state.wins.get(t1, 0) == 1
    assert state.losses.get(t2, 0) == 1
    assert state.wins.get(t2, 0) == 0
    assert state.points_for.get(t1, 0) == 100.0
    assert state.points_against.get(t2, 0) == 100.0


def test_apply_week_end_tie():
    state, (t1, t2, *_) = make_state()
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2)]
    # Both teams score 0 → tie
    state.apply_week_end()
    assert state.ties.get(t1, 0) == 1
    assert state.ties.get(t2, 0) == 1
    assert state.wins.get(t1, 0) == 0


def test_apply_week_end_advances_week():
    state, _ = make_state()
    assert state.current_week == 1
    state.apply_week_end()
    assert state.current_week == 2


def test_apply_week_end_resets_lineups():
    state, (t1, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.set_lineup(t1, ["p1"])
    state.apply_week_end()
    assert state.lineups == {}


# ---------------------------------------------------------------------------
# Snapshot round-trip
# ---------------------------------------------------------------------------


def test_snapshot_roundtrip():
    state, (t1, t2, *_) = make_state()
    state.add_to_roster(t1, "p1")
    state.add_to_roster(t1, "p2")
    state.add_to_roster(t2, "p3")
    state.set_lineup(t1, ["p1"])
    state.deduct_faab(t1, 40)
    state.current_matchups = [MatchupState(home_team_id=t1, away_team_id=t2, home_score=55.0)]

    snap = state.to_snapshot()
    restored = WorldState.from_snapshot(snap)

    assert restored.session_id == state.session_id
    assert restored.current_week == state.current_week
    assert restored.rosters[t1] == {"p1", "p2"}
    assert restored.rosters[t2] == {"p3"}
    assert restored.lineups[t1] == {"p1"}
    assert restored.faab_balances[t1] == 60
    assert restored.current_matchups[0].home_score == 55.0
    assert restored.waiver_priority == state.waiver_priority


def test_snapshot_json_safe():
    """All values in the snapshot dict should be JSON-serializable."""
    import json

    state, _ = make_state()
    snap = state.to_snapshot()
    # Should not raise
    json.dumps(snap)

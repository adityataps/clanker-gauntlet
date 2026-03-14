"""
Tests for FAAB waiver auction resolution — pure unit tests, no DB.
"""

from backend.league.waivers import resolve_faab_auction, resolve_priority_claims
from backend.teams.context import WaiverBid


# Alias so existing tests don't break
def resolve_waiver_auction(bids_by_team, faab_balances, waiver_priority):
    claims, balances, _ = resolve_faab_auction(bids_by_team, faab_balances, waiver_priority)
    return claims, balances


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def bid(add: str, amount: int, priority: int = 1, drop: str | None = None) -> WaiverBid:
    return WaiverBid(add_player_id=add, bid_amount=amount, priority=priority, drop_player_id=drop)


# ---------------------------------------------------------------------------
# Basic resolution
# ---------------------------------------------------------------------------


def test_single_bid_wins():
    bids = {"team1": [bid("player_a", 20)]}
    balances = {"team1": 100}
    priority = ["team1"]

    claims, updated = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 1
    assert claims[0].team_id == "team1"
    assert claims[0].add_player_id == "player_a"
    assert claims[0].bid_amount == 20
    assert updated["team1"] == 80


def test_no_bids_returns_empty():
    claims, updated = resolve_waiver_auction({}, {"team1": 100}, ["team1"])
    assert claims == []
    assert updated == {"team1": 100}


def test_zero_bid_wins_uncontested():
    bids = {"team1": [bid("player_a", 0)]}
    balances = {"team1": 100}
    priority = ["team1"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)
    assert len(claims) == 1
    assert claims[0].bid_amount == 0


# ---------------------------------------------------------------------------
# Highest bidder wins
# ---------------------------------------------------------------------------


def test_highest_bidder_wins_contested_player():
    bids = {
        "team1": [bid("player_a", 10)],
        "team2": [bid("player_a", 25)],
    }
    balances = {"team1": 100, "team2": 100}
    priority = ["team1", "team2"]  # team1 has priority but team2 bids more

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 1
    assert claims[0].team_id == "team2"
    assert claims[0].bid_amount == 25


def test_losing_team_faab_unchanged():
    bids = {
        "team1": [bid("player_a", 10)],
        "team2": [bid("player_a", 25)],
    }
    balances = {"team1": 100, "team2": 100}
    priority = ["team1", "team2"]

    _, updated = resolve_waiver_auction(bids, balances, priority)

    assert updated["team2"] == 75  # paid 25
    assert updated["team1"] == 100  # didn't win, no deduction


# ---------------------------------------------------------------------------
# Tiebreaker: waiver priority
# ---------------------------------------------------------------------------


def test_tie_broken_by_waiver_priority():
    bids = {
        "team_high_priority": [bid("player_a", 20)],
        "team_low_priority": [bid("player_a", 20)],
    }
    balances = {"team_high_priority": 100, "team_low_priority": 100}
    priority = ["team_high_priority", "team_low_priority"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 1
    assert claims[0].team_id == "team_high_priority"


# ---------------------------------------------------------------------------
# Insufficient FAAB
# ---------------------------------------------------------------------------


def test_insufficient_faab_skipped():
    bids = {"team1": [bid("player_a", 50)]}
    balances = {"team1": 10}  # only 10 FAAB, bid is 50
    priority = ["team1"]

    claims, updated = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 0
    assert updated["team1"] == 10  # unchanged


def test_second_bidder_wins_when_first_cant_afford():
    bids = {
        "team1": [bid("player_a", 50)],
        "team2": [bid("player_a", 30)],
    }
    balances = {"team1": 10, "team2": 100}  # team1 can't afford their bid
    priority = ["team1", "team2"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    # team1 bid 50 > team2 bid 30, but team1 can't afford — team2 wins
    assert len(claims) == 1
    assert claims[0].team_id == "team2"


# ---------------------------------------------------------------------------
# Multiple teams, multiple players
# ---------------------------------------------------------------------------


def test_different_teams_win_different_players():
    bids = {
        "team1": [bid("player_a", 20)],
        "team2": [bid("player_b", 30)],
    }
    balances = {"team1": 100, "team2": 100}
    priority = ["team1", "team2"]

    claims, updated = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 2
    claimed_by = {c.add_player_id: c.team_id for c in claims}
    assert claimed_by["player_a"] == "team1"
    assert claimed_by["player_b"] == "team2"
    assert updated["team1"] == 80
    assert updated["team2"] == 70


def test_team_wins_multiple_players():
    bids = {
        "team1": [
            bid("player_a", 20, priority=1),
            bid("player_b", 15, priority=2),
        ],
    }
    balances = {"team1": 100}
    priority = ["team1"]

    claims, updated = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 2
    player_ids = {c.add_player_id for c in claims}
    assert player_ids == {"player_a", "player_b"}
    assert updated["team1"] == 65  # 100 - 20 - 15


def test_player_only_awarded_once():
    bids = {
        "team1": [bid("player_a", 30)],
        "team2": [bid("player_a", 20)],
        "team3": [bid("player_a", 10)],
    }
    balances = {"team1": 100, "team2": 100, "team3": 100}
    priority = ["team1", "team2", "team3"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    # Only one team should win player_a
    winners_of_a = [c for c in claims if c.add_player_id == "player_a"]
    assert len(winners_of_a) == 1
    assert winners_of_a[0].team_id == "team1"


# ---------------------------------------------------------------------------
# Drop player
# ---------------------------------------------------------------------------


def test_claim_includes_drop_player():
    bids = {"team1": [bid("player_a", 20, drop="player_old")]}
    balances = {"team1": 100}
    priority = ["team1"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    assert len(claims) == 1
    assert claims[0].drop_player_id == "player_old"


def test_claim_without_drop_is_none():
    bids = {"team1": [bid("player_a", 20)]}
    balances = {"team1": 100}
    priority = ["team1"]

    claims, _ = resolve_waiver_auction(bids, balances, priority)

    assert claims[0].drop_player_id is None


# ---------------------------------------------------------------------------
# Priority ordering within a team's bids
# ---------------------------------------------------------------------------


def test_higher_bid_amount_processed_before_lower():
    """Team bids more on priority 2 than priority 1 — higher amount wins first."""
    bids = {
        "team1": [
            bid("player_a", 10, priority=1),
            bid("player_b", 40, priority=2),
        ],
        "team2": [bid("player_b", 30)],
    }
    balances = {"team1": 100, "team2": 100}
    priority = ["team2", "team1"]  # team2 has better waiver priority

    claims, updated = resolve_waiver_auction(bids, balances, priority)

    # player_b processed first (highest bid = 40 from team1, beats team2's 30)
    # player_a awarded to team1 uncontested
    b_winner = next(c for c in claims if c.add_player_id == "player_b")
    assert b_winner.team_id == "team1"
    assert updated["team1"] == 100 - 40 - 10


# ---------------------------------------------------------------------------
# Input is not mutated
# ---------------------------------------------------------------------------


def test_original_balances_not_mutated():
    original = {"team1": 100, "team2": 80}
    bids = {"team1": [bid("player_a", 50)]}
    priority = ["team1", "team2"]

    resolve_waiver_auction(bids, original.copy(), priority)

    # original dict should be unchanged
    assert original == {"team1": 100, "team2": 80}


# ---------------------------------------------------------------------------
# Waiver priority resolution
# ---------------------------------------------------------------------------


def pbid(add: str, priority: int = 1, drop: str | None = None) -> WaiverBid:
    """Convenience: priority-mode bid (no dollar amount)."""
    return WaiverBid(add_player_id=add, priority=priority, drop_player_id=drop)


def test_priority_single_claim_wins():
    bids = {"team1": [pbid("player_a")]}
    priority = ["team1"]
    claims, balances, winners = resolve_priority_claims(bids, priority)
    assert len(claims) == 1
    assert claims[0].team_id == "team1"
    assert claims[0].add_player_id == "player_a"
    assert claims[0].bid_amount == 0
    assert balances == {}  # no FAAB in priority mode
    assert winners == {"team1"}


def test_priority_higher_priority_team_wins_contested_player():
    bids = {
        "team1": [pbid("player_a")],
        "team2": [pbid("player_a")],
    }
    priority = ["team1", "team2"]  # team1 is higher priority
    claims, _, winners = resolve_priority_claims(bids, priority)
    assert len(claims) == 1
    assert claims[0].team_id == "team1"
    assert winners == {"team1"}


def test_priority_lower_priority_team_gets_uncontested_player():
    bids = {
        "team1": [pbid("player_a")],
        "team2": [pbid("player_b")],  # different player, uncontested
    }
    priority = ["team1", "team2"]
    claims, _, _ = resolve_priority_claims(bids, priority)
    claimed_by = {c.add_player_id: c.team_id for c in claims}
    assert claimed_by["player_a"] == "team1"
    assert claimed_by["player_b"] == "team2"


def test_priority_one_claim_per_team_per_period():
    """Each team wins at most one player per waiver period."""
    bids = {
        "team1": [
            pbid("player_a", priority=1),
            pbid("player_b", priority=2),
        ],
    }
    priority = ["team1"]
    claims, _, _ = resolve_priority_claims(bids, priority)
    # team1 gets their top choice only
    assert len(claims) == 1
    assert claims[0].add_player_id == "player_a"


def test_priority_fallback_to_second_choice_when_first_taken():
    """If top choice is claimed by a higher-priority team, fall back to second choice."""
    bids = {
        "team1": [pbid("player_a", priority=1)],
        "team2": [
            pbid("player_a", priority=1),  # contested — team1 wins this
            pbid("player_b", priority=2),  # team2 should get this instead
        ],
    }
    priority = ["team1", "team2"]
    claims, _, winners = resolve_priority_claims(bids, priority)
    claimed_by = {c.add_player_id: c.team_id for c in claims}
    assert claimed_by["player_a"] == "team1"
    assert claimed_by["player_b"] == "team2"
    assert winners == {"team1", "team2"}


def test_priority_no_bids_returns_empty():
    claims, balances, winners = resolve_priority_claims({}, ["team1"])
    assert claims == []
    assert winners == set()


def test_priority_drop_player_preserved():
    bids = {"team1": [pbid("player_a", drop="player_old")]}
    claims, _, _ = resolve_priority_claims(bids, ["team1"])
    assert claims[0].drop_player_id == "player_old"


# ---------------------------------------------------------------------------
# Priority reset modes (WorldState)
# ---------------------------------------------------------------------------


def test_rolling_reset_moves_winners_to_bottom():
    import uuid

    from backend.core.world_state import WorldState

    state = WorldState.create(uuid.uuid4(), [uuid.uuid4() for _ in range(4)])
    original_priority = list(state.waiver_priority)
    winner = original_priority[2]  # third team won a claim

    state.apply_rolling_priority_reset({winner})

    # winner is now last
    assert state.waiver_priority[-1] == winner
    # non-winners retain relative order
    non_winners_before = [t for t in original_priority if t != winner]
    non_winners_after = state.waiver_priority[:-1]
    assert non_winners_after == non_winners_before


def test_rolling_reset_multiple_winners():
    import uuid

    from backend.core.world_state import WorldState

    ids = [uuid.uuid4() for _ in range(4)]
    state = WorldState.create(uuid.uuid4(), ids)
    str_ids = state.waiver_priority[:]
    winners = {str_ids[0], str_ids[2]}

    state.apply_rolling_priority_reset(winners)

    # Both winners are at the end; non-winners retain order
    assert set(state.waiver_priority[-2:]) == winners
    assert set(state.waiver_priority[:2]) == {str_ids[1], str_ids[3]}


def test_standings_reset_worst_record_first():
    import uuid

    from backend.core.world_state import WorldState

    ids = [uuid.uuid4() for _ in range(3)]
    state = WorldState.create(uuid.uuid4(), ids)
    str_ids = [str(i) for i in ids]

    # Manually set standings: str_ids[0] is best, str_ids[2] is worst
    state.wins = {str_ids[0]: 5, str_ids[1]: 3, str_ids[2]: 1}
    state.points_for = {str_ids[0]: 800.0, str_ids[1]: 600.0, str_ids[2]: 400.0}

    state.reset_priority_by_standings()

    # Worst record (fewest wins) should be first (highest priority)
    assert state.waiver_priority[0] == str_ids[2]
    assert state.waiver_priority[1] == str_ids[1]
    assert state.waiver_priority[2] == str_ids[0]


def test_standings_reset_tiebreak_by_points_for():
    import uuid

    from backend.core.world_state import WorldState

    ids = [uuid.uuid4() for _ in range(2)]
    state = WorldState.create(uuid.uuid4(), ids)
    str_ids = [str(i) for i in ids]

    # Same record, different points — lower points = higher priority
    state.wins = {str_ids[0]: 3, str_ids[1]: 3}
    state.points_for = {str_ids[0]: 700.0, str_ids[1]: 500.0}

    state.reset_priority_by_standings()

    assert state.waiver_priority[0] == str_ids[1]  # fewer points = higher priority
    assert state.waiver_priority[1] == str_ids[0]

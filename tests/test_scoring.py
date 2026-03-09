"""
Tests for the scoring engine and SportConfig.

All tests are pure (no DB, no network) — they only exercise the scoring
logic and YAML config loading.
"""

import pytest

from backend.core.sport_config import SportConfig
from backend.league.engine import calculate_points, calculate_points_from_event


@pytest.fixture(scope="module")
def scoring():
    return SportConfig.load("nfl").scoring


@pytest.fixture(scope="module")
def config():
    return SportConfig.load("nfl")


# ---------------------------------------------------------------------------
# SportConfig loading
# ---------------------------------------------------------------------------


class TestSportConfig:
    def test_load_nfl(self, config):
        assert config.sport == "nfl"

    def test_roster_slots(self, config):
        assert "QB" in config.roster.slots
        assert "FLEX" in config.roster.slots
        assert "DEF" in config.roster.slots
        assert len(config.roster.slots) == 9

    def test_flex_positions(self, config):
        assert set(config.roster.flex_positions) == {"RB", "WR", "TE"}

    def test_bench_and_ir(self, config):
        assert config.roster.bench_slots == 6
        assert config.roster.ir_slots == 1

    def test_scoring_defaults(self, scoring):
        assert scoring.rec == 0.5  # half-PPR
        assert scoring.pass_yd == 0.04
        assert scoring.rush_td == 6.0

    def test_pts_allow_tiers_loaded(self, scoring):
        assert len(scoring.pts_allow_tiers) == 7

    def test_load_with_overrides(self):
        config = SportConfig.load_with_overrides("nfl", {"rec": 1.0})
        assert config.scoring.rec == 1.0
        # Original unchanged
        assert SportConfig.load("nfl").scoring.rec == 0.5

    def test_missing_sport_raises(self):
        with pytest.raises(FileNotFoundError):
            SportConfig.load("xfl")


# ---------------------------------------------------------------------------
# Skill positions (QB / RB / WR / TE)
# ---------------------------------------------------------------------------


class TestSkillScoring:
    def test_rb_half_ppr(self, scoring):
        # 7 rec × 0.5 + 89 rec_yd × 0.1 + 1 rec_td × 6 + 45 rush_yd × 0.1
        # = 3.5 + 8.9 + 6.0 + 4.5 = 22.9
        stats = {"rec": 7, "rec_yd": 89, "rec_td": 1, "rush_yd": 45}
        assert calculate_points(stats, scoring, "RB") == 22.90

    def test_qb_passing(self, scoring):
        # 280 × 0.04 + 3 × 4 + 22 × 0.1 = 11.2 + 12.0 + 2.2 = 25.4
        stats = {"pass_yd": 280, "pass_td": 3, "rush_yd": 22}
        assert calculate_points(stats, scoring, "QB") == 25.40

    def test_qb_interception_penalty(self, scoring):
        stats = {"pass_yd": 200, "pass_td": 1, "pass_int": 2}
        # 200*0.04 + 4 + 2*(-2) = 8 + 4 - 4 = 8.0
        assert calculate_points(stats, scoring, "QB") == 8.0

    def test_wr_receiving_only(self, scoring):
        stats = {"rec": 5, "rec_yd": 72, "rec_td": 0}
        # 5*0.5 + 72*0.1 = 2.5 + 7.2 = 9.7
        assert calculate_points(stats, scoring, "WR") == 9.70

    def test_te_touchdown(self, scoring):
        stats = {"rec": 4, "rec_yd": 48, "rec_td": 1}
        # 4*0.5 + 48*0.1 + 6 = 2 + 4.8 + 6 = 12.8
        assert calculate_points(stats, scoring, "TE") == 12.80

    def test_fumble_penalty(self, scoring):
        stats = {"rush_yd": 80, "rush_td": 1, "fum_lost": 1}
        # 80*0.1 + 6 + 1*(-2) = 8 + 6 - 2 = 12.0
        assert calculate_points(stats, scoring, "RB") == 12.0

    def test_two_point_conversion(self, scoring):
        stats = {"pass_2pt": 1, "rush_2pt": 1}
        assert calculate_points(stats, scoring, "QB") == 4.0

    def test_return_touchdown(self, scoring):
        stats = {"ret_td": 1}
        assert calculate_points(stats, scoring, "WR") == 6.0

    def test_zero_stats(self, scoring):
        assert calculate_points({}, scoring, "RB") == 0.0

    def test_none_values_treated_as_zero(self, scoring):
        stats = {"rec": None, "rec_yd": None, "rec_td": 1}
        assert calculate_points(stats, scoring, "WR") == 6.0

    def test_full_ppr_override(self):
        config = SportConfig.load_with_overrides("nfl", {"rec": 1.0})
        stats = {"rec": 7, "rec_yd": 89, "rec_td": 1}
        pts = calculate_points(stats, config.scoring, "WR")
        # 7*1.0 + 89*0.1 + 6 = 7 + 8.9 + 6 = 21.9
        assert pts == 21.90

    def test_standard_scoring_override(self):
        config = SportConfig.load_with_overrides("nfl", {"rec": 0.0})
        stats = {"rec": 10, "rec_yd": 100}
        pts = calculate_points(stats, config.scoring, "WR")
        # 10*0 + 100*0.1 = 10.0
        assert pts == 10.0


# ---------------------------------------------------------------------------
# Kicker
# ---------------------------------------------------------------------------


class TestKickerScoring:
    def test_fg_by_distance(self, scoring):
        stats = {"fgm_40_49": 1, "fgm_50_59": 1, "xpm": 2}
        # 4 + 5 + 2 = 11.0
        assert calculate_points(stats, scoring, "K") == 11.0

    def test_missed_fg_penalty(self, scoring):
        stats = {"fgmiss": 1, "xpm": 2}
        # -1 + 2 = 1.0
        assert calculate_points(stats, scoring, "K") == 1.0

    def test_short_fg(self, scoring):
        stats = {"fgm_0_19": 1, "fgm_20_29": 1, "fgm_30_39": 1}
        # 3 + 3 + 3 = 9.0
        assert calculate_points(stats, scoring, "K") == 9.0

    def test_long_fg_60_plus(self, scoring):
        stats = {"fgm_60_plus": 1}
        assert calculate_points(stats, scoring, "K") == 6.0


# ---------------------------------------------------------------------------
# Defense / Special Teams
# ---------------------------------------------------------------------------


class TestDefenseScoring:
    def test_shutout(self, scoring):
        stats = {"sack": 2, "int": 1, "pts_allow": 0}
        # 2 + 2 + 10 = 14.0
        assert calculate_points(stats, scoring, "DEF") == 14.0

    def test_def_touchdown(self, scoring):
        # Sleeper uses "td" for DEF touchdowns
        stats = {"td": 1, "pts_allow": 14}
        # 6 + 1 (tier) = 7.0
        assert calculate_points(stats, scoring, "DEF") == 7.0

    def test_safety(self, scoring):
        stats = {"safe": 1, "pts_allow": 10}
        # 2 + 4 (tier: 7-13 pts) = 6.0
        assert calculate_points(stats, scoring, "DEF") == 6.0

    def test_blocked_kick(self, scoring):
        stats = {"blk_kick": 1, "pts_allow": 21}
        # 2 + 0 (tier: 21-27) = 2.0
        assert calculate_points(stats, scoring, "DEF") == 2.0

    def test_bad_game(self, scoring):
        stats = {"pts_allow": 35}
        # -4 pts (35+ tier)
        assert calculate_points(stats, scoring, "DEF") == -4.0

    def test_fumble_recovery(self, scoring):
        stats = {"fum_rec": 2, "pts_allow": 7}
        # 2*2 + 4 (tier) = 8.0
        assert calculate_points(stats, scoring, "DEF") == 8.0


class TestPtsAllowedTiers:
    """Exhaustive tier boundary tests."""

    @pytest.mark.parametrize(
        "pts_allow,expected",
        [
            (0, 10),
            (1, 7),
            (6, 7),
            (7, 4),
            (13, 4),
            (14, 1),
            (20, 1),
            (21, 0),
            (27, 0),
            (28, -1),
            (34, -1),
            (35, -4),
            (50, -4),
        ],
    )
    def test_tier(self, scoring, pts_allow, expected):
        assert scoring.pts_allowed_score(pts_allow) == expected


# ---------------------------------------------------------------------------
# Position auto-detection
# ---------------------------------------------------------------------------


class TestAutoDetection:
    def test_def_detected_from_pts_allow(self, scoring):
        stats = {"pts_allow": 13, "sack": 2}
        pts = calculate_points(stats, scoring)
        assert pts == 6.0  # 2*1 + 4 (tier)

    def test_def_detected_from_sack(self, scoring):
        stats = {"sack": 3, "int": 1, "pts_allow": 0}
        pts = calculate_points(stats, scoring)
        assert pts == 15.0  # 3 + 2 + 10

    def test_kicker_detected_from_xpm(self, scoring):
        stats = {"xpm": 3, "fgm_30_39": 1}
        pts = calculate_points(stats, scoring)
        assert pts == 6.0  # 3 + 3

    def test_skill_default(self, scoring):
        stats = {"rush_yd": 100, "rush_td": 1}
        pts = calculate_points(stats, scoring)
        assert pts == 16.0  # 100*0.1 + 6


# ---------------------------------------------------------------------------
# Event payload helper
# ---------------------------------------------------------------------------


class TestEventPayloadHelper:
    def test_from_score_update_payload(self, scoring):
        payload = {
            "player_id": "4046",
            "week": 1,
            "pts_half_ppr": 25.4,
            "stats": {"pass_yd": 280, "pass_td": 3, "rush_yd": 22},
        }
        pts = calculate_points_from_event(payload, scoring)
        assert pts == 25.40

    def test_empty_stats_payload(self, scoring):
        payload = {"player_id": "xyz", "week": 1, "stats": {}}
        assert calculate_points_from_event(payload, scoring) == 0.0

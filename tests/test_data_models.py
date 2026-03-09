"""
Unit tests for Pydantic data models (backend/data/models.py).
No DB or network required.
"""

from datetime import UTC, datetime

from backend.data.models import GameEvent, NewsItem, Player, Projection, WaiverPlayer


class TestPlayer:
    def test_basic_construction(self):
        p = Player(player_id="4046", full_name="Patrick Mahomes", position="QB", team="KC")
        assert p.player_id == "4046"
        assert p.display_name == "Patrick Mahomes"

    def test_display_name_falls_back_to_first_last(self):
        p = Player(player_id="1", first_name="Josh", last_name="Allen")
        assert p.display_name == "Josh Allen"

    def test_display_name_falls_back_to_player_id(self):
        p = Player(player_id="unknown-123")
        assert p.display_name == "unknown-123"

    def test_none_fantasy_positions_coerced_to_empty_list(self):
        # Sleeper sometimes returns null for fantasy_positions
        p = Player(player_id="1", fantasy_positions=None)
        assert p.fantasy_positions == []

    def test_fantasy_positions_list_preserved(self):
        p = Player(player_id="1", fantasy_positions=["RB", "WR"])
        assert p.fantasy_positions == ["RB", "WR"]

    def test_is_available_active(self):
        p = Player(player_id="1", status="Active")
        assert p.is_available is True

    def test_is_available_ir(self):
        p = Player(player_id="1", status="IR")
        assert p.is_available is False

    def test_is_available_inactive(self):
        p = Player(player_id="1", status="Inactive")
        assert p.is_available is False

    def test_is_available_none_status(self):
        p = Player(player_id="1", status=None)
        assert p.is_available is True

    def test_extra_sleeper_fields_ignored(self):
        # Sleeper returns many fields we don't use — should not raise
        p = Player(player_id="1", search_rank=5, rotowire_id=999, sportradar_id="xyz")
        assert p.player_id == "1"


class TestProjection:
    def test_basic_construction(self):
        proj = Projection(player_id="4046", week=1, season=2025, pts_half_ppr=21.33)
        assert proj.pts_half_ppr == 21.33

    def test_optional_stat_fields(self):
        proj = Projection(player_id="1", week=1, season=2025)
        assert proj.pass_yd is None
        assert proj.rec is None


class TestNewsItem:
    def test_basic_construction(self):
        item = NewsItem(
            headline="CMC listed questionable",
            published_at=datetime(2025, 10, 1, tzinfo=UTC),
            source="rotoworld",
        )
        assert item.headline == "CMC listed questionable"
        assert item.player_id is None
        assert item.tags == []

    def test_with_player(self):
        item = NewsItem(
            player_id="6794",
            player_name="Christian McCaffrey",
            headline="McCaffrey returns to practice",
            published_at=datetime(2025, 10, 1, tzinfo=UTC),
            source="rotoballer",
            tags=["injury", "RB"],
        )
        assert item.player_id == "6794"
        assert "injury" in item.tags


class TestGameEvent:
    def test_basic_construction(self):
        ev = GameEvent(
            seq=1,
            event_type="SCORE_UPDATE",
            week_number=1,
            sim_offset_hours=108.0,
            payload={"player_id": "4046", "pts_half_ppr": 26.02},
        )
        assert ev.event_type == "SCORE_UPDATE"
        assert ev.payload["player_id"] == "4046"

    def test_empty_payload_default(self):
        ev = GameEvent(seq=1, event_type="WEEK_END", week_number=1, sim_offset_hours=120.0)
        assert ev.payload == {}


class TestWaiverPlayer:
    def test_construction_with_player(self):
        p = Player(player_id="1234", full_name="Gus Edwards", position="RB", team="BAL")
        wp = WaiverPlayer(player=p, trend_adds=342)
        assert wp.player.player_id == "1234"
        assert wp.trend_adds == 342
        assert wp.projection is None
        assert wp.available_in_session is True

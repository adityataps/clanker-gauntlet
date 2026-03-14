"""
WorldState — in-memory representation of a session's league state.

The EventRunner maintains one WorldState per session. It is updated as events
are processed and serialized to JSONB at week boundaries for snapshot/resume.

Design choices:
- Pure Python dataclasses (no SQLAlchemy, no async) — keeps it fast and testable
- team_ids stored as strings throughout (UUID.hex) for JSON round-trip safety
- Roster and lineup are plain sets; matchup scores are tracked per week
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field


@dataclass
class MatchupState:
    """Scores for a single head-to-head matchup."""

    home_team_id: str
    away_team_id: str
    home_score: float = 0.0
    away_score: float = 0.0

    def team_score(self, team_id: str) -> float:
        if team_id == self.home_team_id:
            return self.home_score
        if team_id == self.away_team_id:
            return self.away_score
        return 0.0

    def add_score(self, team_id: str, pts: float) -> None:
        if team_id == self.home_team_id:
            self.home_score += pts
        elif team_id == self.away_team_id:
            self.away_score += pts

    def winner(self) -> str | None:
        """Return winning team_id, or None if tied."""
        if self.home_score > self.away_score:
            return self.home_team_id
        if self.away_score > self.home_score:
            return self.away_team_id
        return None


@dataclass
class WorldState:
    """
    Full league state for a session.

    Attributes:
        session_id:      UUID of the session (as string for JSON compat).
        current_week:    Active scoring week (1-indexed).
        rosters:         team_id -> set of player_ids currently on roster.
        lineups:         team_id -> set of player_ids starting this week.
        faab_balances:   team_id -> remaining FAAB.
        wins:            team_id -> season win count.
        losses:          team_id -> season loss count.
        ties:            team_id -> season tie count.
        points_for:      team_id -> cumulative points scored.
        points_against:  team_id -> cumulative points allowed.
        current_matchups: Active matchups for the current week.
        waiver_priority: Ordered list of team_ids (index 0 = highest priority).
    """

    session_id: str
    current_week: int = 1
    rosters: dict[str, set[str]] = field(default_factory=dict)
    lineups: dict[str, set[str]] = field(default_factory=dict)
    faab_balances: dict[str, int] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    losses: dict[str, int] = field(default_factory=dict)
    ties: dict[str, int] = field(default_factory=dict)
    points_for: dict[str, float] = field(default_factory=dict)
    points_against: dict[str, float] = field(default_factory=dict)
    current_matchups: list[MatchupState] = field(default_factory=list)
    waiver_priority: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Roster management
    # ------------------------------------------------------------------

    def add_to_roster(self, team_id: str, player_id: str) -> None:
        self.rosters.setdefault(team_id, set()).add(player_id)

    def remove_from_roster(self, team_id: str, player_id: str) -> None:
        self.rosters.get(team_id, set()).discard(player_id)
        # Also remove from lineup if benched/dropped
        self.lineups.get(team_id, set()).discard(player_id)

    def transfer_player(self, from_team_id: str, to_team_id: str, player_id: str) -> None:
        self.remove_from_roster(from_team_id, player_id)
        self.add_to_roster(to_team_id, player_id)

    def player_team(self, player_id: str) -> str | None:
        """Return the team_id that owns this player, or None if unowned."""
        for team_id, roster in self.rosters.items():
            if player_id in roster:
                return team_id
        return None

    # ------------------------------------------------------------------
    # Lineup management
    # ------------------------------------------------------------------

    def set_lineup(self, team_id: str, starter_ids: list[str]) -> None:
        """Set the starting lineup for a team. Validates players are on the roster."""
        roster = self.rosters.get(team_id, set())
        valid = [pid for pid in starter_ids if pid in roster]
        self.lineups[team_id] = set(valid)

    def is_starter(self, team_id: str, player_id: str) -> bool:
        return player_id in self.lineups.get(team_id, set())

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def add_player_score(self, player_id: str, pts: float) -> str | None:
        """
        Credit pts to the matchup score of whichever team has this player as a starter.
        Returns the team_id that received the points, or None if none.
        """
        team_id = self.player_team(player_id)
        if team_id is None or not self.is_starter(team_id, player_id):
            return None
        for matchup in self.current_matchups:
            if matchup.home_team_id == team_id or matchup.away_team_id == team_id:
                matchup.add_score(team_id, pts)
                return team_id
        return None

    # ------------------------------------------------------------------
    # FAAB
    # ------------------------------------------------------------------

    def deduct_faab(self, team_id: str, amount: int) -> None:
        self.faab_balances[team_id] = max(0, self.faab_balances.get(team_id, 0) - amount)

    def faab_balance(self, team_id: str) -> int:
        return self.faab_balances.get(team_id, 0)

    # ------------------------------------------------------------------
    # Waiver priority resets
    # ------------------------------------------------------------------

    def apply_rolling_priority_reset(self, winning_team_ids: set[str]) -> None:
        """
        ROLLING reset: teams that won a claim this period drop to the bottom
        of the priority list. Non-winners retain their relative order.
        """
        non_winners = [tid for tid in self.waiver_priority if tid not in winning_team_ids]
        winners = [tid for tid in self.waiver_priority if tid in winning_team_ids]
        self.waiver_priority = non_winners + winners

    def reset_priority_by_standings(self) -> None:
        """
        WEEKLY_STANDINGS reset: re-rank all teams after each week.
        Worst record gets highest priority (first pick). Ties broken by
        points_for ascending (fewer points scored = higher priority).

        Called at WEEK_END after standings have already been updated.
        """
        all_team_ids = list(set(self.wins.keys()) | set(self.waiver_priority))
        all_team_ids.sort(
            key=lambda tid: (
                self.wins.get(tid, 0),
                self.points_for.get(tid, 0.0),
            )
        )
        self.waiver_priority = all_team_ids

    # ------------------------------------------------------------------
    # Week transition
    # ------------------------------------------------------------------

    def apply_week_end(self) -> None:
        """
        Finalize the current week: update standings from matchup results,
        reset lineups, and advance current_week. Call before generating
        next-week matchups.
        """
        for matchup in self.current_matchups:
            h, a = matchup.home_team_id, matchup.away_team_id
            winner = matchup.winner()
            if winner == h:
                self.wins[h] = self.wins.get(h, 0) + 1
                self.losses[a] = self.losses.get(a, 0) + 1
            elif winner == a:
                self.wins[a] = self.wins.get(a, 0) + 1
                self.losses[h] = self.losses.get(h, 0) + 1
            else:  # tie
                self.ties[h] = self.ties.get(h, 0) + 1
                self.ties[a] = self.ties.get(a, 0) + 1

            self.points_for[h] = self.points_for.get(h, 0.0) + matchup.home_score
            self.points_for[a] = self.points_for.get(a, 0.0) + matchup.away_score
            self.points_against[h] = self.points_against.get(h, 0.0) + matchup.away_score
            self.points_against[a] = self.points_against.get(a, 0.0) + matchup.home_score

        # Reset lineups for next week
        self.lineups = {}
        self.current_week += 1

    def generate_matchups(self, team_ids: list[str]) -> None:
        """
        Generate random matchups for the current week.
        With an odd number of teams, one team gets a bye (no matchup).
        """
        shuffled = list(team_ids)
        random.shuffle(shuffled)
        self.current_matchups = []
        for i in range(0, len(shuffled) - 1, 2):
            self.current_matchups.append(
                MatchupState(home_team_id=shuffled[i], away_team_id=shuffled[i + 1])
            )

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        session_id: uuid.UUID,
        team_ids: list[uuid.UUID],
        initial_faab: int = 100,
    ) -> WorldState:
        """
        Create a fresh WorldState for a new session.
        Teams start with empty rosters and full FAAB.
        """
        str_ids = [str(tid) for tid in team_ids]
        state = cls(
            session_id=str(session_id),
            rosters={tid: set() for tid in str_ids},
            lineups={},
            faab_balances=dict.fromkeys(str_ids, initial_faab),
            wins=dict.fromkeys(str_ids, 0),
            losses=dict.fromkeys(str_ids, 0),
            ties=dict.fromkeys(str_ids, 0),
            points_for=dict.fromkeys(str_ids, 0.0),
            points_against=dict.fromkeys(str_ids, 0.0),
            waiver_priority=list(str_ids),
        )
        state.generate_matchups(str_ids)
        return state

    # ------------------------------------------------------------------
    # Snapshot serialization
    # ------------------------------------------------------------------

    def to_snapshot(self) -> dict:
        """Serialize to JSONB-safe dict for DB storage."""
        return {
            "session_id": self.session_id,
            "current_week": self.current_week,
            "rosters": {tid: list(pids) for tid, pids in self.rosters.items()},
            "lineups": {tid: list(pids) for tid, pids in self.lineups.items()},
            "faab_balances": self.faab_balances,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "points_for": self.points_for,
            "points_against": self.points_against,
            "current_matchups": [
                {
                    "home_team_id": m.home_team_id,
                    "away_team_id": m.away_team_id,
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                }
                for m in self.current_matchups
            ],
            "waiver_priority": self.waiver_priority,
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> WorldState:
        """Reconstruct WorldState from a snapshot dict."""
        matchups = [
            MatchupState(
                home_team_id=m["home_team_id"],
                away_team_id=m["away_team_id"],
                home_score=m["home_score"],
                away_score=m["away_score"],
            )
            for m in data.get("current_matchups", [])
        ]
        return cls(
            session_id=data["session_id"],
            current_week=data["current_week"],
            rosters={tid: set(pids) for tid, pids in data.get("rosters", {}).items()},
            lineups={tid: set(pids) for tid, pids in data.get("lineups", {}).items()},
            faab_balances=data.get("faab_balances", {}),
            wins=data.get("wins", {}),
            losses=data.get("losses", {}),
            ties=data.get("ties", {}),
            points_for=data.get("points_for", {}),
            points_against=data.get("points_against", {}),
            current_matchups=matchups,
            waiver_priority=data.get("waiver_priority", []),
        )

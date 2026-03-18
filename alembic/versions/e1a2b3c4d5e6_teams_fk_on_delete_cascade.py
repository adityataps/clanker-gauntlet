"""teams-fk-on-delete-cascade

Revision ID: e1a2b3c4d5e6
Revises: d505c3398f5a
Create Date: 2026-03-17 22:00:00.000000

Changes:
- Add ON DELETE CASCADE to all FK constraints that reference teams.id
  so that deleting a Session (which cascades to Team) cleanly removes
  all session-scoped child rows without FK violations.

Tables affected:
  session_memberships, roster_players, drafts, draft_picks,
  pending_decisions, agent_decisions, matchups (×3),
  player_scores, standings, waiver_bids, trade_proposals (×2)
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1a2b3c4d5e6"
down_revision: str | None = "d505c3398f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each entry: (constraint_name, table, local_col, ondelete)
# nullable FKs use SET NULL so the parent row survives if needed;
# non-nullable FKs use CASCADE to delete the child row.
_FK_CHANGES: list[tuple[str, str, str, str]] = [
    ("session_memberships_team_id_fkey", "session_memberships", "team_id", "SET NULL"),
    ("roster_players_team_id_fkey", "roster_players", "team_id", "CASCADE"),
    ("drafts_turn_team_id_fkey", "drafts", "turn_team_id", "SET NULL"),
    ("draft_picks_team_id_fkey", "draft_picks", "team_id", "CASCADE"),
    ("pending_decisions_team_id_fkey", "pending_decisions", "team_id", "CASCADE"),
    ("agent_decisions_team_id_fkey", "agent_decisions", "team_id", "CASCADE"),
    ("matchups_home_team_id_fkey", "matchups", "home_team_id", "CASCADE"),
    ("matchups_away_team_id_fkey", "matchups", "away_team_id", "CASCADE"),
    ("matchups_winner_team_id_fkey", "matchups", "winner_team_id", "SET NULL"),
    ("player_scores_team_id_fkey", "player_scores", "team_id", "CASCADE"),
    ("standings_team_id_fkey", "standings", "team_id", "CASCADE"),
    ("waiver_bids_team_id_fkey", "waiver_bids", "team_id", "CASCADE"),
    ("trade_proposals_proposing_team_id_fkey", "trade_proposals", "proposing_team_id", "CASCADE"),
    ("trade_proposals_receiving_team_id_fkey", "trade_proposals", "receiving_team_id", "CASCADE"),
]


def upgrade() -> None:
    for constraint, table, col, ondelete in _FK_CHANGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "teams",
            [col],
            ["id"],
            ondelete=ondelete,
        )


def downgrade() -> None:
    # Remove the ondelete behaviour (recreate as plain FK, no action)
    for constraint, table, col, _ondelete in _FK_CHANGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "teams", [col], ["id"])

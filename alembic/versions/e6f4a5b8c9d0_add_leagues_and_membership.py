"""add leagues and membership tables

Revision ID: e6f4a5b8c9d0
Revises: d5e3f4a6b7c8
Create Date: 2026-03-16

Creates leagues, league_memberships, and league_invites tables.
Adds league_id and max_teams columns to sessions.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "e6f4a5b8c9d0"
down_revision = "d5e3f4a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_creation",
            sa.String(50),
            nullable=False,
            server_default="manager_only",
        ),
        sa.Column("max_members", sa.Integer, nullable=False, server_default="100"),
        sa.Column("is_auto_generated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "league_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_league_memberships_league_user", "league_memberships", ["league_id", "user_id"]
    )
    op.create_index("ix_league_memberships_league", "league_memberships", ["league_id"])
    op.create_index("ix_league_memberships_user", "league_memberships", ["user_id"])

    op.create_table(
        "league_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("token", sa.String(128), unique=True, nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=True),
        sa.Column("invited_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_league_invites_token", "league_invites", ["token"], unique=True)
    op.create_index("ix_league_invites_league", "league_invites", ["league_id"])

    op.add_column(
        "sessions",
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("max_teams", sa.Integer, nullable=False, server_default="12"),
    )


def downgrade() -> None:
    op.drop_column("sessions", "max_teams")
    op.drop_column("sessions", "league_id")

    op.drop_index("ix_league_invites_league", table_name="league_invites")
    op.drop_index("ix_league_invites_token", table_name="league_invites")
    op.drop_table("league_invites")

    op.drop_index("ix_league_memberships_user", table_name="league_memberships")
    op.drop_index("ix_league_memberships_league", table_name="league_memberships")
    op.drop_constraint("uq_league_memberships_league_user", "league_memberships", type_="unique")
    op.drop_table("league_memberships")

    op.drop_table("leagues")

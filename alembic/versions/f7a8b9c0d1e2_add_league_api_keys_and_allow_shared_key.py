"""add league_api_keys table and allow_shared_key to leagues

Revision ID: f7a8b9c0d1e2
Revises: e6f4a5b8c9d0
Create Date: 2026-03-16

"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f4a5b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add allow_shared_key flag to leagues
    op.add_column(
        "leagues",
        sa.Column("allow_shared_key", sa.Boolean(), nullable=False, server_default="false"),
    )

    # New table: per-league encrypted API keys (one row per provider)
    op.create_table(
        "league_api_keys",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "league_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
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
    op.create_unique_constraint(
        "uq_league_api_keys_league_provider", "league_api_keys", ["league_id", "provider"]
    )
    op.create_index("ix_league_api_keys_league", "league_api_keys", ["league_id"])


def downgrade() -> None:
    op.drop_index("ix_league_api_keys_league", table_name="league_api_keys")
    op.drop_constraint("uq_league_api_keys_league_provider", "league_api_keys", type_="unique")
    op.drop_table("league_api_keys")
    op.drop_column("leagues", "allow_shared_key")

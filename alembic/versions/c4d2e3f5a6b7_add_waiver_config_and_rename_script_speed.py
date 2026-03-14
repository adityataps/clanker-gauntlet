"""add waiver config and rename script speed values

Revision ID: c4d2e3f5a6b7
Revises: b3c1a2d4e5f6
Create Date: 2026-03-13 00:01:00.000000

- Renames script_speed enum values: instant→blitz, compressed→managed, realtime→immersive
- Adds waiver_mode column (faab | priority), default faab
- Adds priority_reset column (rolling | season_long | weekly_standings), nullable
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d2e3f5a6b7"
down_revision: str | None = "b3c1a2d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Update existing script_speed values to new names
    op.execute("UPDATE sessions SET script_speed = 'blitz' WHERE script_speed = 'instant'")
    op.execute("UPDATE sessions SET script_speed = 'managed' WHERE script_speed = 'compressed'")
    op.execute("UPDATE sessions SET script_speed = 'immersive' WHERE script_speed = 'realtime'")

    # Add waiver_mode column
    op.add_column(
        "sessions",
        sa.Column(
            "waiver_mode",
            sa.String(length=50),
            nullable=False,
            server_default="faab",
        ),
    )

    # Add priority_reset column (nullable — only set when waiver_mode = priority)
    op.add_column(
        "sessions",
        sa.Column("priority_reset", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "priority_reset")
    op.drop_column("sessions", "waiver_mode")

    op.execute("UPDATE sessions SET script_speed = 'instant' WHERE script_speed = 'blitz'")
    op.execute("UPDATE sessions SET script_speed = 'compressed' WHERE script_speed = 'managed'")
    op.execute("UPDATE sessions SET script_speed = 'realtime' WHERE script_speed = 'immersive'")

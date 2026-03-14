"""rename session mode to script_speed

Revision ID: b3c1a2d4e5f6
Revises: 404ee19d7507
Create Date: 2026-03-13 00:00:00.000000

Renames sessions.mode → sessions.script_speed to reflect the user-facing
concept. The enum values (instant, compressed, realtime) are unchanged.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3c1a2d4e5f6"
down_revision: str | None = "404ee19d7507"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("sessions", "mode", new_column_name="script_speed")


def downgrade() -> None:
    op.alter_column("sessions", "script_speed", new_column_name="mode")

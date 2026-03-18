"""structured-traces-dual-stream-routing

Revision ID: d505c3398f5a
Revises: f7a8b9c0d1e2
Create Date: 2026-03-17 20:48:58.080498

Changes:
- agent_decisions.reasoning_trace: TEXT → JSONB (existing rows wrapped via to_jsonb())
- agent_decisions.triggered_by: new JSONB[] column (default [])
- sessions.session_config: new JSONB column (default {})
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d505c3398f5a"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── agent_decisions ──────────────────────────────────────────────────────

    # Cast existing TEXT reasoning_trace values to JSONB.
    # Rows with NULL stay NULL; non-null strings are wrapped as JSON strings.
    op.alter_column(
        "agent_decisions",
        "reasoning_trace",
        existing_type=sa.TEXT(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="to_jsonb(reasoning_trace)",
    )

    op.add_column(
        "agent_decisions",
        sa.Column(
            "triggered_by",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="'[]'::jsonb",
        ),
    )

    # ── sessions ─────────────────────────────────────────────────────────────

    op.add_column(
        "sessions",
        sa.Column(
            "session_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="'{}'::jsonb",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "session_config")
    op.drop_column("agent_decisions", "triggered_by")
    op.alter_column(
        "agent_decisions",
        "reasoning_trace",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.TEXT(),
        existing_nullable=True,
        postgresql_using="reasoning_trace::text",
    )

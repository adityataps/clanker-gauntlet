"""add user_api_keys table and drop anthropic_api_key_enc

Revision ID: d5e3f4a6b7c8
Revises: c4d2e3f5a6b7
Create Date: 2026-03-15

Replaces the single anthropic_api_key_enc column on users with a dedicated
user_api_keys table keyed by (user_id, provider). Supports Anthropic, OpenAI,
and Gemini keys per user.

Existing anthropic_api_key_enc values are migrated to user_api_keys rows with
provider='anthropic' before the column is dropped.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d5e3f4a6b7c8"
down_revision = "c4d2e3f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create user_api_keys table
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
        ),
        sa.Column("encrypted_key", sa.LargeBinary, nullable=False),
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
        "uq_user_api_keys_user_provider", "user_api_keys", ["user_id", "provider"]
    )
    op.create_index("ix_user_api_keys_user", "user_api_keys", ["user_id"])

    # 2. Migrate existing anthropic keys into the new table
    op.execute(
        """
        INSERT INTO user_api_keys (id, user_id, provider, encrypted_key, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            id,
            'anthropic',
            anthropic_api_key_enc,
            NOW(),
            NOW()
        FROM users
        WHERE anthropic_api_key_enc IS NOT NULL
        """
    )

    # 3. Drop the old column
    op.drop_column("users", "anthropic_api_key_enc")


def downgrade() -> None:
    # Re-add the column
    op.add_column(
        "users",
        sa.Column("anthropic_api_key_enc", sa.LargeBinary, nullable=True),
    )

    # Restore Anthropic keys from user_api_keys
    op.execute(
        """
        UPDATE users u
        SET anthropic_api_key_enc = k.encrypted_key
        FROM user_api_keys k
        WHERE k.user_id = u.id AND k.provider = 'anthropic'
        """
    )

    op.drop_index("ix_user_api_keys_user", table_name="user_api_keys")
    op.drop_constraint("uq_user_api_keys_user_provider", "user_api_keys")
    op.drop_table("user_api_keys")

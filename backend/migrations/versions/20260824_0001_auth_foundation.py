"""Create the account, invitation, session and auth rate-limit tables.

Revision ID: 20260824_0001
Revises:
Create Date: 2026-08-24 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_digest"),
    )
    op.create_index("ix_invitations_code_digest", "invitations", ["code_digest"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("csrf_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_token_digest", "sessions", ["token_digest"], unique=False)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)
    op.create_index("ix_sessions_revoked_at", "sessions", ["revoked_at"], unique=False)
    op.create_table(
        "auth_rate_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action", "key_digest", name="uq_auth_rate_limits_action_key"),
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
    op.drop_index("ix_sessions_revoked_at", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_token_digest", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_invitations_code_digest", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

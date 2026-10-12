"""Add email verification and password reset tokens.

Revision ID: 20260827_0009
Revises: 20260827_0008
Create Date: 2026-08-27 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0009"
down_revision: str | Sequence[str] | None = "20260827_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_token_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(f"ix_{name}_user_id", name, ["user_id"], unique=False)
    op.create_index(f"ix_{name}_token_digest", name, ["token_digest"], unique=True)
    op.create_index(f"ix_{name}_expires_at", name, ["expires_at"], unique=False)
    op.create_index(f"ix_{name}_used_at", name, ["used_at"], unique=False)


def _drop_token_table(name: str) -> None:
    op.drop_index(f"ix_{name}_used_at", table_name=name)
    op.drop_index(f"ix_{name}_expires_at", table_name=name)
    op.drop_index(f"ix_{name}_token_digest", table_name=name)
    op.drop_index(f"ix_{name}_user_id", table_name=name)
    op.drop_table(name)


def upgrade() -> None:
    _create_token_table("email_verification_tokens")
    _create_token_table("password_reset_tokens")


def downgrade() -> None:
    _drop_token_table("password_reset_tokens")
    _drop_token_table("email_verification_tokens")

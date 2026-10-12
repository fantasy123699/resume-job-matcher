"""Add scheduled account deletion requests.

Revision ID: 20260827_0007
Revises: 20260826_0006
Create Date: 2026-08-27 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0007"
down_revision: str | Sequence[str] | None = "20260826_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_account_deletion_requests_scheduled_for",
        "account_deletion_requests",
        ["scheduled_for"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_deletion_requests_scheduled_for", table_name="account_deletion_requests"
    )
    op.drop_table("account_deletion_requests")

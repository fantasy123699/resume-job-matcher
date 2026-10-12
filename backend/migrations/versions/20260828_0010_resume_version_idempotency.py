"""Add idempotency keys to resume versions.

Revision ID: 20260828_0010
Revises: 20260827_0009
Create Date: 2026-08-28 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0010"
down_revision: str | Sequence[str] | None = "20260827_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_versions", sa.Column("idempotency_key", sa.String(length=128), nullable=True)
    )
    op.create_unique_constraint(
        "uq_resume_versions_user_idempotency_key",
        "resume_versions",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_resume_versions_user_idempotency_key", "resume_versions", type_="unique")
    op.drop_column("resume_versions", "idempotency_key")

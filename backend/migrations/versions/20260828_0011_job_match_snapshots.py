"""Persist immutable job-match snapshots.

Revision ID: 20260828_0011
Revises: 20260828_0010
Create Date: 2026-08-28 22:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0011"
down_revision: str | Sequence[str] | None = "20260828_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_description_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_description_id"], ["job_descriptions.id"]),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "resume_profile_id",
            "job_description_id",
            "algorithm_version",
            name="uq_job_matches_user_resume_job_algorithm",
        ),
    )
    op.create_index(
        op.f("ix_job_matches_job_description_id"), "job_matches", ["job_description_id"]
    )
    op.create_index(op.f("ix_job_matches_resume_profile_id"), "job_matches", ["resume_profile_id"])
    op.create_index(op.f("ix_job_matches_user_id"), "job_matches", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_job_matches_user_id"), table_name="job_matches")
    op.drop_index(op.f("ix_job_matches_resume_profile_id"), table_name="job_matches")
    op.drop_index(op.f("ix_job_matches_job_description_id"), table_name="job_matches")
    op.drop_table("job_matches")

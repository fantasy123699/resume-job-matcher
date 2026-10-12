"""Add immutable, source-backed resume version snapshots.

Revision ID: 20260826_0005
Revises: 20260824_0004
Create Date: 2026-08-26 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_0005"
down_revision: str | Sequence[str] | None = "20260824_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_profile_id", sa.Uuid(), nullable=False),
        sa.Column("job_description_id", sa.Uuid(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "accepted_suggestion_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_description_id"], ["job_descriptions.id"]),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_versions_user_id", "resume_versions", ["user_id"], unique=False)
    op.create_index(
        "ix_resume_versions_resume_profile_id",
        "resume_versions",
        ["resume_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_resume_versions_job_description_id",
        "resume_versions",
        ["job_description_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_resume_versions_job_description_id", table_name="resume_versions")
    op.drop_index("ix_resume_versions_resume_profile_id", table_name="resume_versions")
    op.drop_index("ix_resume_versions_user_id", table_name="resume_versions")
    op.drop_table("resume_versions")

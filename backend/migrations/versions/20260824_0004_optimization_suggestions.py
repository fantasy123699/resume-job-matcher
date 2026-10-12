"""Add source-backed optimization suggestions and user decisions.

Revision ID: 20260824_0004
Revises: 20260824_0003
Create Date: 2026-08-26 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0004"
down_revision: str | Sequence[str] | None = "20260824_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_profile_id", sa.Uuid(), nullable=False),
        sa.Column("job_description_id", sa.Uuid(), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resume_fact_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("job_requirement_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=False),
        sa.Column(
            "requires_user_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("user_decision", sa.String(length=16), nullable=False, server_default="pending"),
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
        sa.ForeignKeyConstraint(["job_description_id"], ["job_descriptions.id"]),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_optimization_suggestions_user_id", "optimization_suggestions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_optimization_suggestions_resume_profile_id",
        "optimization_suggestions",
        ["resume_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_optimization_suggestions_job_description_id",
        "optimization_suggestions",
        ["job_description_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_optimization_suggestions_job_description_id", table_name="optimization_suggestions"
    )
    op.drop_index(
        "ix_optimization_suggestions_resume_profile_id", table_name="optimization_suggestions"
    )
    op.drop_index("ix_optimization_suggestions_user_id", table_name="optimization_suggestions")
    op.drop_table("optimization_suggestions")

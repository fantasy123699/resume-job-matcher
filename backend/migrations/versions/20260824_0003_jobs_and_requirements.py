"""Add pasted job descriptions and source-backed technology requirements.

Revision ID: 20260824_0003
Revises: 20260824_0002
Create Date: 2026-08-24 00:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0003"
down_revision: str | Sequence[str] | None = "20260824_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_descriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_descriptions_user_id", "job_descriptions", ["user_id"], unique=False)
    op.create_table(
        "job_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_description_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_type", sa.String(length=32), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_location", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["job_description_id"], ["job_descriptions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_requirements_user_id", "job_requirements", ["user_id"], unique=False)
    op.create_index(
        "ix_job_requirements_job_description_id",
        "job_requirements",
        ["job_description_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_requirements_job_description_id", table_name="job_requirements")
    op.drop_index("ix_job_requirements_user_id", table_name="job_requirements")
    op.drop_table("job_requirements")
    op.drop_index("ix_job_descriptions_user_id", table_name="job_descriptions")
    op.drop_table("job_descriptions")

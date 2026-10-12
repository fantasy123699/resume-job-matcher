"""Add structured resume profiles and source-backed facts.

Revision ID: 20260824_0002
Revises: 20260824_0001
Create Date: 2026-08-24 00:01:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0002"
down_revision: str | Sequence[str] | None = "20260824_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending_confirmation",
        ),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_profiles_user_id", "resume_profiles", ["user_id"], unique=False)
    op.create_table(
        "resume_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_profile_id", sa.Uuid(), nullable=False),
        sa.Column("fact_type", sa.String(length=32), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_location", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("user_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_facts_user_id", "resume_facts", ["user_id"], unique=False)
    op.create_index(
        "ix_resume_facts_resume_profile_id", "resume_facts", ["resume_profile_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_resume_facts_resume_profile_id", table_name="resume_facts")
    op.drop_index("ix_resume_facts_user_id", table_name="resume_facts")
    op.drop_table("resume_facts")
    op.drop_index("ix_resume_profiles_user_id", table_name="resume_profiles")
    op.drop_table("resume_profiles")

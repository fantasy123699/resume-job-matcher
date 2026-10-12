"""Add durable agent runs and approval checkpoints.

Revision ID: 20260827_0008
Revises: 20260827_0007
Create Date: 2026-08-27 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0008"
down_revision: str | Sequence[str] | None = "20260827_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_profile_id", sa.Uuid(), nullable=False),
        sa.Column("job_description_id", sa.Uuid(), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=48), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"], unique=False)
    op.create_index(
        "ix_agent_runs_resume_profile_id", "agent_runs", ["resume_profile_id"], unique=False
    )
    op.create_index(
        "ix_agent_runs_job_description_id", "agent_runs", ["job_description_id"], unique=False
    )
    op.create_index("ix_agent_runs_state", "agent_runs", ["state"], unique=False)
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_checkpoints_user_id", "agent_checkpoints", ["user_id"], unique=False)
    op.create_index(
        "ix_agent_checkpoints_agent_run_id", "agent_checkpoints", ["agent_run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_agent_checkpoints_agent_run_id", table_name="agent_checkpoints")
    op.drop_index("ix_agent_checkpoints_user_id", table_name="agent_checkpoints")
    op.drop_table("agent_checkpoints")
    op.drop_index("ix_agent_runs_state", table_name="agent_runs")
    op.drop_index("ix_agent_runs_job_description_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_resume_profile_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_table("agent_runs")

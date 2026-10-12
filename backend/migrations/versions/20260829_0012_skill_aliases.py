"""Add the skill_aliases reference table.

Revision ID: 20260829_0012
Revises: 20260828_0011
Create Date: 2026-08-29 10:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0012"
down_revision: str | Sequence[str] | None = "20260828_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Intentionally not seeded here: the bundled seed in
    # ``domain.skill_dictionary`` is always unioned in at load time, so
    # importing application code into a migration would only make this
    # revision non-reproducible. Use the ``sync-skill-aliases`` CLI command to
    # materialise the seed for inspection and editing.
    op.create_table(
        "skill_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.String(length=100), nullable=False),
        sa.Column("alias", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", "alias", name="uq_skill_aliases_canonical_alias"),
    )
    op.create_index(op.f("ix_skill_aliases_canonical_name"), "skill_aliases", ["canonical_name"])
    op.create_index(op.f("ix_skill_aliases_alias"), "skill_aliases", ["alias"])
    op.create_index(op.f("ix_skill_aliases_status"), "skill_aliases", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_aliases_status"), table_name="skill_aliases")
    op.drop_index(op.f("ix_skill_aliases_alias"), table_name="skill_aliases")
    op.drop_index(op.f("ix_skill_aliases_canonical_name"), table_name="skill_aliases")
    op.drop_table("skill_aliases")

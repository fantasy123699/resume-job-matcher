"""Add retained DOCX export records.

Revision ID: 20260826_0006
Revises: 20260826_0005
Create Date: 2026-08-26 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0006"
down_revision: str | Sequence[str] | None = "20260826_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("storage_name", sa.String(length=128), nullable=False),
        sa.Column("download_name", sa.String(length=200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_name"),
    )
    op.create_index("ix_document_exports_user_id", "document_exports", ["user_id"], unique=False)
    op.create_index(
        "ix_document_exports_resume_version_id",
        "document_exports",
        ["resume_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_exports_expires_at", "document_exports", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_document_exports_expires_at", table_name="document_exports")
    op.drop_index("ix_document_exports_resume_version_id", table_name="document_exports")
    op.drop_index("ix_document_exports_user_id", table_name="document_exports")
    op.drop_table("document_exports")

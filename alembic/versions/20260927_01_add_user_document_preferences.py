"""Add per-user document archive preferences.

Revision ID: 20260927_01
Revises: 20260926_01
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260927_01"
down_revision: str | None = "20260926_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"users", "documents"}.issubset(tables):
        raise RuntimeError("Existing users and documents tables are required")
    if "user_document_preferences" in tables:
        return

    op.create_table(
        "user_document_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_user_document_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_user_document_preferences_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_document_preferences"),
        sa.UniqueConstraint(
            "user_id", "document_id",
            name="uq_user_document_preferences_user_document",
        ),
    )
    op.create_index(
        "ix_user_document_preferences_user_archived",
        "user_document_preferences",
        ["user_id", "is_archived"],
        unique=False,
    )
    op.create_index(
        "ix_user_document_preferences_document_id",
        "user_document_preferences",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "user_document_preferences" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("user_document_preferences")

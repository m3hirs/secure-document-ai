"""Add the Stage 9 authentication persistence foundation.

Revision ID: 20260926_01
Revises: None
Create Date: 2026-09-26

This first revision targets the existing Secure Document AI schema. It adds
only nullable user authentication fields and the new session table. Conditional
checks make recovery safe if the interrupted Stage 9 work created part of the
new schema, without dropping or recreating existing application tables.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        raise RuntimeError(
            "The existing users table is required before applying this revision"
        )

    user_columns = _column_names(inspector, "users")
    if "password_hash" not in user_columns:
        op.add_column(
            "users",
            sa.Column("password_hash", sa.String(length=255), nullable=True),
        )
    if "password_changed_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "password_changed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
    if "last_login_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "last_login_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    inspector = sa.inspect(bind)
    if "user_sessions" not in set(inspector.get_table_names()):
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "last_seen_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_user_sessions_user_id_users",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
            sa.UniqueConstraint(
                "token_hash",
                name="uq_user_sessions_token_hash",
            ),
        )

    inspector = sa.inspect(bind)
    session_indexes = {
        index["name"]
        for index in inspector.get_indexes("user_sessions")
    }
    if "ix_user_sessions_token_hash" not in session_indexes:
        op.create_index(
            "ix_user_sessions_token_hash",
            "user_sessions",
            ["token_hash"],
            unique=False,
        )
    if "ix_user_sessions_user_id" not in session_indexes:
        op.create_index(
            "ix_user_sessions_user_id",
            "user_sessions",
            ["user_id"],
            unique=False,
        )
    if "ix_user_sessions_expires_at" not in session_indexes:
        op.create_index(
            "ix_user_sessions_expires_at",
            "user_sessions",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_sessions" in set(inspector.get_table_names()):
        op.drop_table("user_sessions")

    inspector = sa.inspect(bind)
    if "users" not in set(inspector.get_table_names()):
        return
    user_columns = _column_names(inspector, "users")
    for column_name in (
        "last_login_at",
        "password_changed_at",
        "password_hash",
    ):
        if column_name in user_columns:
            op.drop_column("users", column_name)

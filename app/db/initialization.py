"""Transitional non-destructive schema initialization for local development.

Alembic is the migration source of truth for authentication and per-user
document preference schema.
``create_all`` remains temporarily for compatibility with an existing schema,
but excludes authentication tables and refuses an empty-schema bootstrap.
Remove startup DDL after all deployed databases are managed and stamped by
Alembic.
"""
from sqlalchemy import inspect, text

from app.db.database import Base, engine
from app.db import models  # noqa: F401 - registers all metadata models


_DOCUMENT_COLUMNS = {
    "processing_status": "VARCHAR(30) NOT NULL DEFAULT 'uploaded'",
    "processing_started_at": "TIMESTAMP WITH TIME ZONE",
    "processed_at": "TIMESTAMP WITH TIME ZONE",
    "extracted_text_length": "INTEGER NOT NULL DEFAULT 0",
    "text_page_count": "INTEGER NOT NULL DEFAULT 0",
    "image_count": "INTEGER NOT NULL DEFAULT 0",
    "ocr_page_count": "INTEGER NOT NULL DEFAULT 0",
    "processing_error": "TEXT",
    "chunking_status": "VARCHAR(30) NOT NULL DEFAULT 'pending'",
    "chunked_at": "TIMESTAMP WITH TIME ZONE",
    "chunk_count": "INTEGER NOT NULL DEFAULT 0",
    "chunking_error": "TEXT",
    "chunking_version": "VARCHAR(50)",
    "embedding_status": "VARCHAR(30) NOT NULL DEFAULT 'pending'",
    "embedded_at": "TIMESTAMP WITH TIME ZONE",
    "embedding_count": "INTEGER NOT NULL DEFAULT 0",
    "embedding_error": "TEXT",
    "embedding_version": "VARCHAR(100)",
}


def _startup_managed_tables():
    """Return legacy tables that startup may check without owning auth DDL."""
    return tuple(
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {"user_sessions", "user_document_preferences"}
    )


def initialize_database() -> None:
    """Maintain the existing schema without creating authentication schema."""
    if not inspect(engine).has_table("users"):
        raise RuntimeError(
            "Database schema is missing; initialize it through migrations"
        )
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    # Existing tables are not altered by create_all, so the new nullable auth
    # columns remain Alembic-owned. Explicit exclusions prevent startup from
    # creating migration-owned tables before their reviewed revisions.
    Base.metadata.create_all(engine, tables=_startup_managed_tables())
    with engine.begin() as connection:
        for name, definition in _DOCUMENT_COLUMNS.items():
            connection.execute(text(f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {name} {definition}"))

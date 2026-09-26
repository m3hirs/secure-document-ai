from collections.abc import Generator
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.models import User, UserSession


@pytest.fixture
def isolated_auth_db() -> Generator[Session, None, None]:
    """Reproducible Stage 9 schema isolated from configured PostgreSQL."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    UserSession.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_postgresql_test_database():
    """Apply the real auth revision only to the dedicated integration DB."""
    test_database_name = "secure_document_ai_test"
    test_url = make_url(get_settings().database_url).set(
        database=test_database_name
    )
    engine = create_engine(test_url)
    try:
        with engine.begin() as connection:
            actual_database = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()
            if actual_database != test_database_name:
                raise RuntimeError(
                    "Refusing to migrate a database outside the dedicated test target"
                )
            context = MigrationContext.configure(connection)
            operations = Operations(context)
            revision_path = (
                Path(__file__).resolve().parents[1]
                / "alembic"
                / "versions"
                / "20260926_01_add_authentication_foundation.py"
            )
            spec = spec_from_file_location("stage9_auth_revision", revision_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Unable to load the Stage 9 auth revision")
            revision = module_from_spec(spec)
            spec.loader.exec_module(revision)
            with operations.context(context):
                revision.upgrade()
        yield test_url
    finally:
        engine.dispose()

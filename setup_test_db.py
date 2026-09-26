"""Create tables in the isolated PostgreSQL test database only."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.database import Base
from app.db import models  # noqa: F401 - register SQLAlchemy models


TEST_DATABASE_NAME = "secure_document_ai_test"

# Read existing connection settings without changing .env.
development_url = make_url(get_settings().database_url)

# Build a separate URL that differs only in database name.
test_url = development_url.set(database=TEST_DATABASE_NAME)

# Never use the application's default engine for test setup.
test_engine = create_engine(test_url, pool_pre_ping=True)

try:
    with test_engine.connect() as connection:
        actual_database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if actual_database != TEST_DATABASE_NAME:
            raise RuntimeError(
                f"REFUSING TO CONTINUE: connected to {actual_database!r}, "
                f"expected {TEST_DATABASE_NAME!r}"
            )

        extension_exists = connection.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                ")"
            )
        ).scalar_one()

        if not extension_exists:
            raise RuntimeError(
                "pgvector is not enabled in the test database."
            )

    print(f"Verified isolated database: {actual_database}")
    print("Creating missing test tables...")

    Base.metadata.create_all(bind=test_engine)

    print("Test database tables created successfully.")

finally:
    test_engine.dispose()
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Classification, Document, Team, User
from app.services.semantic_search_service import document_accessible_clause


TEST_DATABASE_NAME = "secure_document_ai_test"


def test_document_access_against_postgresql(migrated_postgresql_test_database):
    # Build a separate connection; never use the application's default engine.
    test_url = make_url(get_settings().database_url).set(
        database=TEST_DATABASE_NAME
    )
    test_engine = create_engine(test_url)

    try:
        with test_engine.connect() as connection:
            actual_database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            assert actual_database == TEST_DATABASE_NAME, (
                f"REFUSING TEST: connected to {actual_database!r}"
            )

        # This transaction is rolled back when the test finishes.
        with test_engine.connect() as connection:
            transaction = connection.begin()

            try:
                with Session(bind=connection) as db:
                    software = Team(name="Test Software")
                    design = Team(name="Test Design")

                    ava = User(
                        name="Test Ava",
                        email="test-ava-stage5@example.invalid",
                        teams=[software],
                    )

                    noah = User(
                        name="Test Noah",
                        email="test-noah-stage5@example.invalid",
                        teams=[design],
                    )

                    classification = Classification(
                        name="Test Restricted"
                    )

                    db.add_all([ava, noah, classification])
                    db.flush()

                    shared_document = Document(
                        filename="shared.pdf",
                        file_path="test-stage5/shared.pdf",
                        file_type="pdf",
                        file_size=100,
                        classification=classification,
                        uploader=ava,
                        uploaded_at=datetime.now(timezone.utc),
                        teams=[software, design],
                    )

                    restricted_document = Document(
                        filename="restricted.pdf",
                        file_path="test-stage5/restricted.pdf",
                        file_type="pdf",
                        file_size=100,
                        classification=classification,
                        uploader=noah,
                        uploaded_at=datetime.now(timezone.utc),
                        teams=[design],
                    )

                    db.add_all([shared_document, restricted_document])
                    db.flush()

                    # Ava belongs only to Software.
                    ava_documents = db.scalars(
                        select(Document).where(
                            document_accessible_clause(ava.id)
                        )
                    ).all()

                    ava_document_ids = {
                        document.id for document in ava_documents
                    }

                    assert shared_document.id in ava_document_ids
                    assert restricted_document.id not in ava_document_ids

                    # Noah belongs only to Design.
                    noah_documents = db.scalars(
                        select(Document).where(
                            document_accessible_clause(noah.id)
                        )
                    ).all()

                    noah_document_ids = {
                        document.id for document in noah_documents
                    }

                    assert shared_document.id in noah_document_ids
                    assert restricted_document.id in noah_document_ids

            finally:
                transaction.rollback()

    finally:
        test_engine.dispose()

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import Principal, get_current_principal, require_csrf_protection
from app.db.database import get_db
from app.db.models import (
    Classification,
    Document,
    DocumentChunk,
    DocumentPage,
    Tag,
    Team,
    User,
    UserDocumentPreference,
    document_tags,
    document_teams,
    user_teams,
)
from app.main import app
from app.services.document_search_service import search_documents
from app.services.natural_search_parser import ParsedSearch
from app.services.rag_service import INSUFFICIENT_EVIDENCE_ANSWER, answer_question
from app.services.semantic_search_service import (
    SearchResult,
    document_active_workspace_clause,
    semantic_search,
)


DOCUMENT_ID = 31
RESTRICTED_DOCUMENT_ID = 35


@pytest.fixture
def archive_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        User.__table__,
        Team.__table__,
        Classification.__table__,
        Tag.__table__,
        user_teams,
        Document.__table__,
        document_tags,
        document_teams,
        UserDocumentPreference.__table__,
        DocumentPage.__table__,
        DocumentChunk.__table__,
    ):
        table.create(engine)

    with Session(engine, expire_on_commit=False) as db:
        software = Team(id=1, name="Software")
        design = Team(id=2, name="Design")
        first = User(id=1, name="First User", email="first@example.test", teams=[software])
        second = User(id=2, name="Second User", email="second@example.test", teams=[software])
        designer = User(id=3, name="Designer", email="designer@example.test", teams=[design])
        classification = Classification(id=1, name="Internal")
        now = datetime.now(timezone.utc)
        shared = Document(
            id=DOCUMENT_ID,
            filename="shared.pdf",
            file_path="tests/shared.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=first,
            uploaded_at=now,
            teams=[software],
        )
        restricted = Document(
            id=RESTRICTED_DOCUMENT_ID,
            filename="design-only.pdf",
            file_path="tests/design-only.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=designer,
            uploaded_at=now,
            teams=[design],
        )
        shared_page = DocumentPage(
            id=311,
            document=shared,
            page_number=1,
            extracted_text="Shared workspace evidence",
            has_text=True,
        )
        restricted_page = DocumentPage(
            id=351,
            document=restricted,
            page_number=1,
            extracted_text="Restricted workspace evidence",
            has_text=True,
        )
        db.add_all(
            [
                shared,
                restricted,
                second,
                DocumentChunk(
                    id=3111,
                    document=shared,
                    page=shared_page,
                    chunk_index=0,
                    text="Shared workspace evidence",
                    character_count=25,
                    source_start_char=0,
                    source_end_char=25,
                ),
                DocumentChunk(
                    id=3511,
                    document=restricted,
                    page=restricted_page,
                    chunk_index=0,
                    text="Restricted workspace evidence",
                    character_count=29,
                    source_start_char=0,
                    source_end_char=29,
                ),
            ]
        )
        db.commit()

        identity = {"user_id": 1}

        def override_db():
            yield db

        def override_principal():
            return Principal(user_id=identity["user_id"])

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        app.dependency_overrides[require_csrf_protection] = lambda: None
        client = TestClient(app)
        try:
            yield client, db, identity
        finally:
            client.close()
            app.dependency_overrides.clear()
    engine.dispose()


def test_archive_hides_only_current_users_document(archive_client):
    client, _, identity = archive_client
    response = client.post(f"/documents/{DOCUMENT_ID}/archive", json={})
    assert response.status_code == 200
    assert response.json()["is_archived"] is True
    assert client.get("/documents").json() == []

    identity["user_id"] = 2
    other_list = client.get("/documents")
    assert other_list.status_code == 200
    assert [item["id"] for item in other_list.json()] == [DOCUMENT_ID]
    assert other_list.json()[0]["is_archived"] is False


def test_archived_list_and_direct_detail_show_only_current_state(archive_client):
    client, _, identity = archive_client
    assert client.post(f"/documents/{DOCUMENT_ID}/archive", json={}).status_code == 200
    archived = client.get("/documents?include_archived=true").json()
    assert [(item["id"], item["is_archived"]) for item in archived] == [(DOCUMENT_ID, True)]
    assert client.get(f"/documents/{DOCUMENT_ID}").json()["is_archived"] is True

    identity["user_id"] = 2
    assert client.get(f"/documents/{DOCUMENT_ID}").json()["is_archived"] is False


def test_restore_returns_document_to_normal_list(archive_client):
    client, _, _ = archive_client
    client.post(f"/documents/{DOCUMENT_ID}/archive", json={})
    response = client.post(f"/documents/{DOCUMENT_ID}/restore", json={})
    assert response.status_code == 200
    assert response.json()["is_archived"] is False
    assert [item["id"] for item in client.get("/documents").json()] == [DOCUMENT_ID]


def test_unauthorized_and_restricted_ids_fail_with_generic_404(archive_client):
    client, _, identity = archive_client
    restricted = client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/archive", json={})
    assert restricted.status_code == 404
    assert restricted.json() == {"detail": "Document not found"}

    identity["user_id"] = 3
    unauthorized = client.post(f"/documents/{DOCUMENT_ID}/archive", json={})
    assert unauthorized.status_code == 404
    assert unauthorized.json() == {"detail": "Document not found"}


def test_client_cannot_archive_for_another_user(archive_client):
    client, db, _ = archive_client
    response = client.post(f"/documents/{DOCUMENT_ID}/archive", json={"user_id": 2})
    assert response.status_code == 422
    assert db.scalar(select(func.count(UserDocumentPreference.id))) == 0


def test_archive_does_not_modify_shared_document_or_team_relations(archive_client):
    client, db, _ = archive_client
    before_document_count = db.scalar(select(func.count(Document.id)))
    before_team_links = db.scalar(select(func.count()).select_from(document_teams))
    assert client.post(f"/documents/{DOCUMENT_ID}/archive", json={}).status_code == 200
    assert db.scalar(select(func.count(Document.id))) == before_document_count
    assert db.scalar(select(func.count()).select_from(document_teams)) == before_team_links
    preference = db.scalar(select(UserDocumentPreference))
    assert preference is not None
    assert preference.user_id == 1
    assert preference.document_id == DOCUMENT_ID
    assert preference.archived_at is not None


def test_archive_and_restore_openapi_require_csrf_and_no_identity():
    schema = app.openapi()
    for path in (
        "/documents/{document_id}/archive",
        "/documents/{document_id}/restore",
    ):
        operation = schema["paths"][path]["post"]
        parameters = operation.get("parameters", [])
        assert any(parameter.get("name") == "X-CSRF-Token" for parameter in parameters)
        assert "user_id" not in str(operation)


def _metadata_query() -> ParsedSearch:
    return ParsedSearch(
        topic=None,
        file_type=None,
        uploader_id=None,
        team_id=None,
        classification_id=None,
        tag_id=None,
        start=None,
        end=None,
        mode="metadata",
    )


def test_active_workspace_sql_is_per_user_and_restore_reenables_natural_search(archive_client):
    client, db, identity = archive_client
    assert client.post(f"/documents/{DOCUMENT_ID}/archive", json={}).status_code == 200

    user_a_ids = set(db.scalars(select(Document.id).where(document_active_workspace_clause(1))))
    user_b_ids = set(db.scalars(select(Document.id).where(document_active_workspace_clause(2))))
    assert DOCUMENT_ID not in user_a_ids
    assert DOCUMENT_ID in user_b_ids
    assert RESTRICTED_DOCUMENT_ID not in user_a_ids
    assert RESTRICTED_DOCUMENT_ID not in user_b_ids

    assert search_documents(db, 1, _metadata_query(), 1, 10) == []
    assert [row[0].id for row in search_documents(db, 2, _metadata_query(), 1, 10)] == [DOCUMENT_ID]

    identity["user_id"] = 1
    assert client.post(f"/documents/{DOCUMENT_ID}/restore", json={}).status_code == 200
    assert [row[0].id for row in search_documents(db, 1, _metadata_query(), 1, 10)] == [DOCUMENT_ID]


def test_semantic_search_statement_applies_archive_and_team_filters_before_results():
    db = Mock()
    db.execute.return_value.all.return_value = []
    settings = SimpleNamespace(
        semantic_search_top_k=5,
        semantic_search_max_top_k=10,
        semantic_search_min_similarity=0.70,
        embedding_version="test-v1",
    )
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.embed_query", return_value=[0.0] * 384),
    ):
        assert semantic_search(db, 17, "workspace evidence", 5) == []

    statement = db.execute.call_args.args[0]
    compiled = statement.compile()
    sql = str(compiled).casefold()
    assert "document_teams" in sql
    assert "user_teams" in sql
    assert "user_document_preferences" in sql
    assert "is_archived" in sql
    assert 17 in compiled.params.values()


def test_hybrid_search_statement_applies_active_workspace_filter():
    db = Mock()
    db.execute.return_value.all.return_value = []
    parsed = ParsedSearch(
        topic="workspace evidence",
        file_type="application/pdf",
        uploader_id=None,
        team_id=None,
        classification_id=None,
        tag_id=None,
        start=None,
        end=None,
        mode="hybrid",
    )
    with (
        patch(
            "app.services.document_search_service.get_settings",
            return_value=SimpleNamespace(
                embedding_version="test-v1",
                semantic_search_min_similarity=0.70,
            ),
        ),
        patch("app.services.document_search_service.embed_query", return_value=[0.0] * 384),
    ):
        assert search_documents(db, 23, parsed, 1, 10) == []

    statement = db.execute.call_args.args[0]
    compiled = statement.compile()
    sql = str(compiled).casefold()
    assert "user_document_preferences" in sql
    assert "is_archived" in sql
    assert "document_teams" in sql
    assert 23 in compiled.params.values()


def test_rag_sources_follow_per_user_archive_and_restore_state(archive_client):
    client, db, identity = archive_client

    def active_search(db, user_id, query, top_k):
        del query
        rows = db.execute(
            select(DocumentChunk, DocumentPage, Document)
            .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(document_active_workspace_clause(user_id))
            .order_by(Document.id)
            .limit(top_k)
        ).all()
        return [
            SearchResult(
                document_id=document.id,
                filename=document.filename,
                page_number=page.page_number,
                chunk_id=chunk.id,
                chunk_text=chunk.text,
                similarity_score=1.0,
            )
            for chunk, page, document in rows
        ]

    assert client.post(f"/documents/{DOCUMENT_ID}/archive", json={}).status_code == 200
    with (
        patch("app.services.rag_service.semantic_search", side_effect=active_search),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Supported by the active workspace.", "source_ids": ["S1"]},
        ) as generator,
    ):
        archived_result = answer_question(db, 1, "What is in the shared workspace file?")
        assert archived_result.answer == INSUFFICIENT_EVIDENCE_ANSWER
        assert archived_result.sources == []
        generator.assert_not_called()

        other_user_result = answer_question(db, 2, "What is in the shared workspace file?")
        assert [source.document_id for source in other_user_result.sources] == [DOCUMENT_ID]
        assert RESTRICTED_DOCUMENT_ID not in {source.document_id for source in other_user_result.sources}

        identity["user_id"] = 1
        assert client.post(f"/documents/{DOCUMENT_ID}/restore", json={}).status_code == 200
        restored_result = answer_question(db, 1, "What is in the shared workspace file?")
        assert [source.document_id for source in restored_result.sources] == [DOCUMENT_ID]

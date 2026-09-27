from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import security
from app.core.config import Settings
from app.core.security import (
    Principal,
    SessionPrincipal,
    get_current_principal,
    require_csrf_protection,
)
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
    UserSession,
    document_tags,
    document_teams,
    user_teams,
)
from app.main import app
from app.services.auth_service import create_session, hash_password, utc_now
from app.services.rag_service import INSUFFICIENT_EVIDENCE_ANSWER
from app.services.semantic_search_service import SearchResult, document_accessible_clause


ORIGIN = "http://localhost:5173"
SOFTWARE_USER_ID = 101
DESIGN_USER_ID = 102
ACCESSIBLE_DOCUMENT_ID = 301
RESTRICTED_DOCUMENT_ID = 302


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        frontend_allowed_origins=[ORIGIN],
        session_absolute_timeout_minutes=60,
        session_idle_timeout_minutes=15,
    )


@pytest.fixture
def authorization_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        User.__table__,
        UserSession.__table__,
        Team.__table__,
        Classification.__table__,
        Tag.__table__,
        user_teams,
        Document.__table__,
        UserDocumentPreference.__table__,
        document_tags,
        document_teams,
        DocumentPage.__table__,
        DocumentChunk.__table__,
    ]
    for table in tables:
        table.create(engine)

    with Session(engine, expire_on_commit=False) as db:
        software = Team(id=201, name="Software")
        design = Team(id=202, name="Design")
        user_a = User(
            id=SOFTWARE_USER_ID,
            name="Software User",
            email="software@example.com",
            password_hash=hash_password("software-password"),
            teams=[software],
        )
        user_b = User(
            id=DESIGN_USER_ID,
            name="Design User",
            email="design@example.com",
            password_hash=hash_password("design-password"),
            teams=[design],
        )
        classification = Classification(id=401, name="Internal")
        now = datetime.now(timezone.utc)
        accessible = Document(
            id=ACCESSIBLE_DOCUMENT_ID,
            filename="software.pdf",
            file_path="tests/software.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=user_a,
            uploaded_at=now,
            teams=[software],
            processing_status="processed",
            extracted_text_length=18,
            text_page_count=1,
            chunking_status="completed",
            chunk_count=1,
            embedding_status="completed",
            embedding_count=1,
        )
        restricted = Document(
            id=RESTRICTED_DOCUMENT_ID,
            filename="design.pdf",
            file_path="tests/design.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=user_b,
            uploaded_at=now,
            teams=[design],
            processing_status="processed",
            extracted_text_length=18,
            text_page_count=1,
            chunking_status="completed",
            chunk_count=1,
            embedding_status="completed",
            embedding_count=1,
        )
        accessible_page = DocumentPage(
            id=501,
            document=accessible,
            page_number=1,
            extracted_text="ACCESSIBLE-CONTENT",
            has_text=True,
        )
        restricted_page = DocumentPage(
            id=502,
            document=restricted,
            page_number=1,
            extracted_text="RESTRICTED-CONTENT",
            has_text=True,
        )
        db.add_all(
            [
                accessible,
                restricted,
                DocumentChunk(
                    id=601,
                    document=accessible,
                    page=accessible_page,
                    chunk_index=0,
                    text="ACCESSIBLE-CONTENT",
                    character_count=18,
                    source_start_char=0,
                    source_end_char=18,
                ),
                DocumentChunk(
                    id=602,
                    document=restricted,
                    page=restricted_page,
                    chunk_index=0,
                    text="RESTRICTED-CONTENT",
                    character_count=18,
                    source_start_char=0,
                    source_end_char=18,
                ),
            ]
        )
        db.commit()
        yield db
    engine.dispose()


@pytest.fixture
def authorized_client(authorization_db):
    identity = {"user_id": SOFTWARE_USER_ID}

    def override_db():
        yield authorization_db

    def override_principal():
        return Principal(user_id=identity["user_id"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = override_principal
    app.dependency_overrides[require_csrf_protection] = lambda: None
    client = TestClient(app)
    try:
        yield client, identity, authorization_db
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_all_protected_route_groups_reject_missing_cookie():
    def fake_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)
    requests = [
        (
            "post",
            "/documents/upload",
            {
                "data": {"classification_id": "1"},
                "files": {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
            },
        ),
        (
            "post",
            "/documents/upload-bulk",
            {
                "data": {"classification_id": "1"},
                "files": [("files", ("test.pdf", b"%PDF-1.4", "application/pdf"))],
            },
        ),
        ("get", "/documents", {}),
        ("get", "/documents/1", {}),
        ("get", "/documents/1/processing", {}),
        ("get", "/documents/1/pages", {}),
        ("get", "/documents/1/chunking", {}),
        ("get", "/documents/1/chunks", {}),
        ("get", "/documents/1/embedding", {}),
        ("post", "/documents/1/rechunk", {}),
        ("post", "/documents/1/embed", {}),
        ("post", "/search/semantic", {"json": {"query": "test"}}),
        ("post", "/search/documents", {"json": {"query": "test"}}),
        ("post", "/documents/1/summarize", {}),
        ("post", "/documents/ask", {"json": {"question": "test"}}),
        ("get", "/users", {}),
        ("get", "/users/1", {}),
        ("get", "/teams", {}),
    ]
    try:
        for method, path, kwargs in requests:
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == 401, (method, path, response.text)
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_software_user_document_matrix_is_404_and_design_user_succeeds(authorized_client):
    client, identity, _, = authorized_client
    list_response = client.get("/documents")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [ACCESSIBLE_DOCUMENT_ID]

    restricted_gets = [
        f"/documents/{RESTRICTED_DOCUMENT_ID}",
        f"/documents/{RESTRICTED_DOCUMENT_ID}/processing",
        f"/documents/{RESTRICTED_DOCUMENT_ID}/pages",
        f"/documents/{RESTRICTED_DOCUMENT_ID}/chunking",
        f"/documents/{RESTRICTED_DOCUMENT_ID}/chunks",
        f"/documents/{RESTRICTED_DOCUMENT_ID}/embedding",
    ]
    for path in restricted_gets:
        assert client.get(path).status_code == 404

    with (
        patch("app.api.documents.rechunk_document") as rechunk,
        patch("app.api.documents.embed_document") as embed,
    ):
        assert client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/rechunk").status_code == 404
        assert client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/embed").status_code == 404
        rechunk.assert_not_called()
        embed.assert_not_called()

    identity["user_id"] = DESIGN_USER_ID
    for path in restricted_gets:
        assert client.get(path).status_code == 200
    with (
        patch("app.api.documents.rechunk_document", side_effect=lambda db, document: document),
        patch("app.api.documents.embed_document", side_effect=lambda db, document: document),
    ):
        assert client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/rechunk").status_code == 200
        assert client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/embed").status_code == 200


def test_search_receives_only_trusted_identity_and_rejects_injected_user_id(authorized_client):
    client, identity, db = authorized_client

    def filtered_semantic(db, user_id, query, top_k):
        documents = db.scalars(
            select(Document).where(document_accessible_clause(user_id)).order_by(Document.id)
        ).all()
        return [
            SearchResult(
                document_id=document.id,
                filename=document.filename,
                page_number=1,
                chunk_id=601 if document.id == ACCESSIBLE_DOCUMENT_ID else 602,
                chunk_text="authorized synthetic text",
                similarity_score=0.9,
            )
            for document in documents
        ]

    with patch("app.api.search.semantic_search", side_effect=filtered_semantic):
        response = client.post("/search/semantic", json={"query": "test"})
        assert [item["document_id"] for item in response.json()["results"]] == [
            ACCESSIBLE_DOCUMENT_ID
        ]
        injected = client.post(
            "/search/semantic", json={"query": "test", "user_id": DESIGN_USER_ID}
        )
        assert injected.status_code == 422

        identity["user_id"] = DESIGN_USER_ID
        response = client.post("/search/semantic", json={"query": "test"})
        assert [item["document_id"] for item in response.json()["results"]] == [
            RESTRICTED_DOCUMENT_ID
        ]

    natural_injected = client.post(
        "/search/documents", json={"query": "test", "user_id": SOFTWARE_USER_ID}
    )
    assert natural_injected.status_code == 422

    parsed = SimpleNamespace(
        mode="metadata",
        file_type=None,
        uploader_id=None,
        team_id=None,
        classification_id=None,
        tag_id=None,
        start=None,
        end=None,
    )

    def filtered_natural(db, user_id, parsed, page, page_size):
        documents = db.scalars(
            select(Document).where(document_accessible_clause(user_id)).order_by(Document.id)
        ).all()
        return [(document, None, None, None) for document in documents]

    identity["user_id"] = SOFTWARE_USER_ID
    with (
        patch("app.api.search.parse_query", return_value=parsed),
        patch("app.api.search.search_document_results", side_effect=filtered_natural),
    ):
        response = client.post("/search/documents", json={"query": "test"})
        assert [item["document_id"] for item in response.json()["results"]] == [
            ACCESSIBLE_DOCUMENT_ID
        ]
        identity["user_id"] = DESIGN_USER_ID
        response = client.post("/search/documents", json={"query": "test"})
        assert [item["document_id"] for item in response.json()["results"]] == [
            RESTRICTED_DOCUMENT_ID
        ]


def test_summary_checks_authorization_before_pages_or_llm(authorized_client):
    client, identity, _ = authorized_client
    with patch("app.services.summarization_service.generate_local_summary") as llm:
        response = client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/summarize")
        assert response.status_code == 404
        llm.assert_not_called()

        identity["user_id"] = DESIGN_USER_ID
        llm.return_value = "- supported\n- local\n- summary"
        response = client.post(f"/documents/{RESTRICTED_DOCUMENT_ID}/summarize")
        assert response.status_code == 200
        llm.assert_called_once_with("RESTRICTED-CONTENT")


def test_rag_never_passes_restricted_content_for_software_user(authorized_client):
    client, identity, db = authorized_client

    def filtered_results(db, user_id, query, top_k):
        documents = db.scalars(
            select(Document).where(document_accessible_clause(user_id)).order_by(Document.id)
        ).all()
        return [
            SearchResult(
                document_id=document.id,
                filename=document.filename,
                page_number=1,
                chunk_id=601 if document.id == ACCESSIBLE_DOCUMENT_ID else 602,
                chunk_text="ACCESSIBLE-CONTENT" if document.id == ACCESSIBLE_DOCUMENT_ID else "RESTRICTED-CONTENT",
                similarity_score=0.9,
            )
            for document in documents
        ]

    with (
        patch("app.services.rag_service.semantic_search", side_effect=filtered_results),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Supported [S1].", "source_ids": ["S1"]},
        ) as llm,
    ):
        response = client.post("/documents/ask", json={"question": "What is supported?"})
        assert response.status_code == 200
        assert [source["document_id"] for source in response.json()["sources"]] == [
            ACCESSIBLE_DOCUMENT_ID
        ]
        context = llm.call_args.args[1]
        assert "RESTRICTED-CONTENT" not in context

        identity["user_id"] = DESIGN_USER_ID
        response = client.post("/documents/ask", json={"question": "What is supported?"})
        assert response.status_code == 200
        assert [source["document_id"] for source in response.json()["sources"]] == [
            RESTRICTED_DOCUMENT_ID
        ]


def test_empty_authorized_rag_retrieval_never_calls_ollama(authorized_client):
    client, _, _ = authorized_client
    with (
        patch("app.services.rag_service.semantic_search", return_value=[]),
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        response = client.post("/documents/ask", json={"question": "Restricted only?"})
    assert response.status_code == 200
    assert response.json()["answer"] == INSUFFICIENT_EVIDENCE_ANSWER
    assert response.json()["sources"] == []
    llm.assert_not_called()


def test_upload_ignores_client_uploader_and_uses_principal(authorized_client):
    client, _, db = authorized_client
    document = db.get(Document, ACCESSIBLE_DOCUMENT_ID)
    with patch("app.api.documents._upload_one", return_value=document) as upload:
        response = client.post(
            "/documents/upload",
            data={
                "classification_id": "401",
                "team_ids": "201",
                "uploaded_by": str(DESIGN_USER_ID),
            },
            files={"file": ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
    assert response.status_code == 201
    assert upload.call_args.args[2] == SOFTWARE_USER_ID


def test_upload_rejects_missing_team_selection(authorized_client):
    client, _, _ = authorized_client
    with patch("app.api.documents._upload_one") as upload:
        response = client.post(
            "/documents/upload",
            data={"classification_id": "401"},
            files={"file": ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
    assert response.status_code == 422
    upload.assert_not_called()


def test_upload_rejects_team_outside_principal_membership(authorized_client):
    client, _, _ = authorized_client
    response = client.post(
        "/documents/upload",
        data={"classification_id": "401", "team_ids": "202"},
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 403


def test_bulk_upload_rejects_team_outside_principal_membership_before_processing(authorized_client):
    client, _, _ = authorized_client
    with patch("app.api.documents._upload_one") as upload:
        response = client.post(
            "/documents/upload-bulk",
            data={"classification_id": "401", "team_ids": "202"},
            files=[("files", ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )
    assert response.status_code == 403
    upload.assert_not_called()


def test_mutation_csrf_and_origin_are_enforced(authorization_db, monkeypatch):
    settings = _settings()
    user = authorization_db.get(User, SOFTWARE_USER_ID)
    created = create_session(authorization_db, user, settings=settings)
    authorization_db.commit()

    def override_db():
        yield authorization_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: SessionPrincipal(
        user_id=SOFTWARE_USER_ID,
        session_id=created.session.id,
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    client = TestClient(app)
    client.cookies.set(settings.session_cookie_name, created.token)
    try:
        path = f"/documents/{ACCESSIBLE_DOCUMENT_ID}/rechunk"
        assert client.post(path).status_code == 403
        assert client.post(
            path,
            headers={"Origin": "https://evil.example", "X-CSRF-Token": created.csrf_token},
        ).status_code == 403
        assert client.post(
            path,
            headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
        ).status_code == 403
        with patch(
            "app.api.documents.rechunk_document", side_effect=lambda db, document: document
        ):
            response = client.post(
                path,
                headers={"Origin": ORIGIN, "X-CSRF-Token": created.csrf_token},
            )
        assert response.status_code == 200
        archive_path = f"/documents/{ACCESSIBLE_DOCUMENT_ID}/archive"
        assert client.post(archive_path, json={}).status_code == 403
        archive_response = client.post(
            archive_path,
            json={},
            headers={"Origin": ORIGIN, "X-CSRF-Token": created.csrf_token},
        )
        assert archive_response.status_code == 200
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_exact_credentialed_cors_policy():
    client = TestClient(app)
    allowed = client.options(
        "/documents",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-CSRF-Token",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in allowed.headers["access-control-allow-headers"].lower()

    rejected = client.options(
        "/documents",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in rejected.headers
    client.close()


def test_openapi_removes_uploader_identity_and_documents_csrf_policy():
    schema = app.openapi()
    upload_operation = schema["paths"]["/documents/upload"]["post"]
    bulk_operation = schema["paths"]["/documents/upload-bulk"]["post"]
    assert "uploaded_by" not in str(upload_operation)
    assert "uploaded_by" not in str(bulk_operation)

    persistent_mutations = [
        ("/documents/upload", "post"),
        ("/documents/upload-bulk", "post"),
        ("/documents/{document_id}/rechunk", "post"),
        ("/documents/{document_id}/embed", "post"),
        ("/documents/{document_id}/archive", "post"),
        ("/documents/{document_id}/restore", "post"),
        ("/auth/logout", "post"),
    ]
    for path, method in persistent_mutations:
        parameters = schema["paths"][path][method].get("parameters", [])
        assert any(parameter.get("name") == "X-CSRF-Token" for parameter in parameters)

    computational_posts = [
        ("/search/semantic", "post"),
        ("/search/documents", "post"),
        ("/documents/{document_id}/summarize", "post"),
        ("/documents/ask", "post"),
    ]
    for path, method in computational_posts:
        parameters = schema["paths"][path][method].get("parameters", [])
        assert not any(parameter.get("name") == "X-CSRF-Token" for parameter in parameters)


def test_session_states_control_protected_route_access(authorization_db, monkeypatch):
    settings = _settings()

    def override_db():
        yield authorization_db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    client = TestClient(app)
    user = authorization_db.get(User, SOFTWARE_USER_ID)
    try:
        assert client.get("/documents").status_code == 401
        client.cookies.set(settings.session_cookie_name, "invalid")
        assert client.get("/documents").status_code == 401

        revoked = create_session(authorization_db, user, settings=settings)
        revoked.session.revoked_at = utc_now()
        expired = create_session(authorization_db, user, settings=settings)
        expired.session.expires_at = utc_now() - timedelta(seconds=1)
        idle = create_session(authorization_db, user, settings=settings)
        idle.session.last_seen_at = utc_now() - timedelta(minutes=16)
        valid = create_session(authorization_db, user, settings=settings)
        authorization_db.commit()

        client.cookies.set(settings.session_cookie_name, revoked.token)
        assert client.get("/documents").status_code == 401
        client.cookies.set(settings.session_cookie_name, expired.token)
        assert client.get("/documents").status_code == 401
        client.cookies.set(settings.session_cookie_name, idle.token)
        assert client.get("/documents").status_code == 401
        client.cookies.set(settings.session_cookie_name, valid.token)
        assert client.get("/documents").status_code == 200

        user.is_active = False
        authorization_db.commit()
        assert client.get("/documents").status_code == 401
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_changing_valid_session_changes_only_sql_authorized_documents(
    authorization_db, monkeypatch
):
    settings = _settings()
    software_session = create_session(
        authorization_db,
        authorization_db.get(User, SOFTWARE_USER_ID),
        settings=settings,
    )
    design_session = create_session(
        authorization_db,
        authorization_db.get(User, DESIGN_USER_ID),
        settings=settings,
    )
    authorization_db.commit()

    def override_db():
        yield authorization_db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    client = TestClient(app)
    try:
        client.cookies.set(settings.session_cookie_name, software_session.token)
        software_ids = [item["id"] for item in client.get("/documents").json()]
        client.cookies.set(settings.session_cookie_name, design_session.token)
        design_ids = [item["id"] for item in client.get("/documents").json()]
    finally:
        client.close()
        app.dependency_overrides.clear()
    assert software_ids == [ACCESSIBLE_DOCUMENT_ID]
    assert design_ids == [RESTRICTED_DOCUMENT_ID]


def test_user_and_team_directory_is_authenticated_and_safe(authorized_client):
    client, _, _ = authorized_client
    users = client.get("/users")
    teams = client.get("/teams")
    assert users.status_code == 200
    assert teams.status_code == 200
    assert [team["id"] for team in teams.json()] == [201]
    forbidden_fields = {
        "password_hash",
        "password_changed_at",
        "last_login_at",
        "token_hash",
        "csrf_token_hash",
        "session_id",
    }
    assert not forbidden_fields.intersection(users.text)
    assert not forbidden_fields.intersection(teams.text)

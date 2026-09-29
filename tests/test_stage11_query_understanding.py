from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.db.models import (
    Classification,
    Document,
    DocumentChunk,
    DocumentPage,
    Team,
    User,
    UserDocumentPreference,
    document_teams,
    user_teams,
)
from app.main import app
from app.services.entity_presence_service import (
    detect_named_target_question,
    resolve_authorized_named_target,
)
from app.services.query_normalization import (
    lexical_query_tokens,
    normalize_document_name,
)
from app.services.rag_service import classify_rag_intent
from app.services.semantic_search_service import (
    SearchResult,
    _LexicalHit,
    hybrid_search,
    lexical_search,
)


KRUTRIM_MODEL = "hf.co/bartowski/krutrim-ai-labs_Krutrim-2-instruct-GGUF:Q4_K_M"


def _add_document(
    db: Session,
    *,
    document_id: int,
    filename: str,
    team: Team,
    uploader: User,
    classification: Classification,
    text: str,
) -> None:
    document = Document(
        id=document_id,
        filename=filename,
        file_path=f"tests/stage11-{document_id}.pdf",
        file_type="application/pdf",
        file_size=100,
        page_count=1,
        classification=classification,
        uploader=uploader,
        uploaded_at=datetime.now(timezone.utc),
        teams=[team],
        processing_status="processed",
    )
    page = DocumentPage(
        id=document_id * 10,
        document=document,
        page_number=1,
        extracted_text=text,
        has_text=True,
    )
    db.add(DocumentChunk(
        id=document_id * 100,
        document=document,
        page=page,
        chunk_index=0,
        text=text,
        character_count=len(text),
        source_start_char=0,
        source_end_char=len(text),
    ))


@pytest.fixture
def stage11_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        User.__table__,
        Team.__table__,
        Classification.__table__,
        user_teams,
        Document.__table__,
        document_teams,
        UserDocumentPreference.__table__,
        DocumentPage.__table__,
        DocumentChunk.__table__,
    ):
        table.create(engine)

    with Session(engine, expire_on_commit=False) as db:
        software = Team(id=1, name="Software")
        design = Team(id=2, name="Design")
        user = User(id=1, name="Ava", email="ava@stage11.test", teams=[software])
        colleague = User(id=2, name="Noah", email="noah@stage11.test", teams=[software])
        outsider = User(id=3, name="Priya", email="priya@stage11.test", teams=[design])
        classification = Classification(id=1, name="Internal")
        db.add_all([user, colleague, outsider, classification])
        _add_document(
            db,
            document_id=11,
            filename="Enterprise_Document_1.pdf",
            team=software,
            uploader=user,
            classification=classification,
            text="Enterprise platform controls and approved architecture.",
        )
        _add_document(
            db,
            document_id=12,
            filename="Aarav-Mehta-Resume.pdf",
            team=software,
            uploader=user,
            classification=classification,
            text="Aarav Mehta. Languages: Python. Frameworks: FastAPI.",
        )
        _add_document(
            db,
            document_id=35,
            filename="Restricted_Enterprise_Document_1.pdf",
            team=design,
            uploader=outsider,
            classification=classification,
            text="Restricted design evidence.",
        )
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize(
    "value",
    [
        "Enterprise_Document_1.pdf",
        "enterprise document 1",
        "Enterprise-Document-One",
        "enterprise_document_1",
    ],
)
def test_document_name_variants_share_a_conservative_key(value):
    assert normalize_document_name(value) == "enterprise document 1"


def test_lexical_tokens_share_number_and_separator_normalization():
    assert lexical_query_tokens("enterprise-document-one.pdf") == ("enterprise", "1")


@pytest.mark.parametrize(
    ("question", "target"),
    [
        ("summary of enterprise document 1", "enterprise document 1"),
        ("summarize enterprise document 1", "enterprise document 1"),
        ("summarise Enterprise_Document_1.pdf", "Enterprise_Document_1"),
        ("tell me about enterprise document one", "enterprise document one"),
        ("what is in enterprise-document-1", "enterprise-document-1"),
        ("technologies in Aarav Mehta resume", "Aarav Mehta"),
        ("explain the document called Enterprise Document 1", "Enterprise Document 1"),
        ("information from Enterprise_Document_1.pdf", "Enterprise_Document_1"),
        ("Aarav Mehta resum", "Aarav Mehta resum"),
    ],
)
def test_named_document_variants_are_decomposed(question, target):
    intent = detect_named_target_question(question)
    assert intent is not None
    assert intent.entity == target
    assert intent.topic is not None
    classified = classify_rag_intent(question)
    assert classified.kind == "named_document"
    assert classified.entity == target


@pytest.mark.parametrize(
    "target",
    [
        "Enterprise_Document_1.pdf",
        "enterprise document 1",
        "Enterprise-Document-One",
        "enterprise_document_1",
        "Enterprize document 1",
    ],
)
def test_authorized_filename_resolution_handles_safe_variants(stage11_db, target):
    resolution = resolve_authorized_named_target(stage11_db, 1, target)
    assert resolution.document_ids == (11,)
    assert resolution.ambiguous is False


def test_resume_typo_resolves_only_inside_authorized_workspace(stage11_db):
    resolution = resolve_authorized_named_target(stage11_db, 1, "Aarav Mehta resum")
    assert resolution.document_ids == (12,)
    assert 35 not in resolution.document_ids


def test_archived_target_is_excluded_but_other_users_archive_state_is_independent(stage11_db):
    stage11_db.add(UserDocumentPreference(user_id=1, document_id=11, is_archived=True))
    stage11_db.commit()
    assert resolve_authorized_named_target(stage11_db, 1, "enterprise document 1").document_ids == ()
    assert resolve_authorized_named_target(stage11_db, 2, "enterprise document 1").document_ids == (11,)


def test_ambiguous_normalized_filenames_fail_closed(stage11_db):
    _add_document(
        stage11_db,
        document_id=13,
        filename="Enterprise-Document-One.pdf",
        team=stage11_db.get(Team, 1),
        uploader=stage11_db.get(User, 1),
        classification=stage11_db.get(Classification, 1),
        text="A second enterprise document.",
    )
    stage11_db.commit()
    resolution = resolve_authorized_named_target(stage11_db, 1, "enterprise document 1")
    assert resolution.document_ids == ()
    assert resolution.ambiguous is True


def _result(document_id: int, chunk_id: int, text: str, score: float) -> SearchResult:
    return SearchResult(document_id, f"document-{document_id}.pdf", 1, chunk_id, text, score)


def test_hybrid_rrf_prefers_strong_exact_lexical_evidence_and_deduplicates_chunks():
    lexical = _LexicalHit(_result(1, 10, "Project Falcon", 1.0), 2.0, True)
    semantic_unrelated = _result(2, 20, "Other project", 0.95)
    semantic_duplicate = _result(1, 10, "Project Falcon", 0.88)
    settings = SimpleNamespace(
        semantic_search_top_k=5,
        semantic_search_max_top_k=50,
        semantic_search_min_similarity=0.81,
    )
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.lexical_search", return_value=[lexical]),
        patch(
            "app.services.semantic_search_service.semantic_search",
            return_value=[semantic_unrelated, semantic_duplicate],
        ),
    ):
        results = hybrid_search(Mock(), 7, "Project Falcon", 5)
    assert [result.chunk_id for result in results] == [10, 20]


def test_hybrid_supports_lexical_only_and_strong_semantic_only_hits():
    lexical = _LexicalHit(_result(1, 10, "literal hit", 0.9), 1.0, False)
    settings = SimpleNamespace(
        semantic_search_top_k=5,
        semantic_search_max_top_k=50,
        semantic_search_min_similarity=0.81,
    )
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.lexical_search", return_value=[lexical]),
        patch("app.services.semantic_search_service.semantic_search", return_value=[]),
    ):
        assert [item.document_id for item in hybrid_search(Mock(), 7, "literal", 5)] == [1]
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.lexical_search", return_value=[]),
        patch(
            "app.services.semantic_search_service.semantic_search",
            return_value=[_result(2, 20, "semantic topic", 0.91)],
        ),
    ):
        assert [item.document_id for item in hybrid_search(Mock(), 7, "backend engineering", 5)] == [2]


def test_nonsense_weak_semantic_only_neighbor_is_rejected():
    settings = SimpleNamespace(
        semantic_search_top_k=5,
        semantic_search_max_top_k=50,
        semantic_search_min_similarity=0.81,
    )
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.lexical_search", return_value=[]),
        patch(
            "app.services.semantic_search_service.semantic_search",
            return_value=[_result(2, 20, "unrelated resume", 0.82)],
        ),
    ):
        assert hybrid_search(Mock(), 7, "quantum banana farming satellite recipe", 5) == []


def test_multilingual_semantic_only_query_is_not_forced_through_latin_lexical_gate():
    settings = SimpleNamespace(
        semantic_search_top_k=5,
        semantic_search_max_top_k=50,
        semantic_search_min_similarity=0.81,
    )
    with (
        patch("app.services.semantic_search_service.get_settings", return_value=settings),
        patch("app.services.semantic_search_service.lexical_search", return_value=[]),
        patch(
            "app.services.semantic_search_service.semantic_search",
            return_value=[_result(4, 40, "authorized multilingual evidence", 0.82)],
        ),
    ):
        results = hybrid_search(Mock(), 7, "जिम्मेदार एआई निगरानी", 5)
    assert [item.document_id for item in results] == [4]


def test_lexical_sql_contains_team_archive_and_document_scope_filters():
    db = Mock()
    db.execute.return_value.all.return_value = []
    lexical_search(db, 17, "Enterprise Document One", 5, document_ids=(11,))
    compiled = db.execute.call_args.args[0].compile()
    sql = str(compiled).casefold()
    assert "document_teams" in sql
    assert "user_teams" in sql
    assert "user_document_preferences" in sql
    assert "documents.id" in sql
    assert 17 in compiled.params.values()


def test_named_document_api_binds_sources_and_failed_resolution_skips_ollama(stage11_db):
    def override_db():
        yield stage11_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=1)
    client = TestClient(app)
    result = _result(11, 1100, "Enterprise platform controls.", 0.95)
    try:
        with (
            patch("app.services.rag_service.semantic_search", return_value=[result]) as retrieval,
            patch(
                "app.services.rag_service.generate_local_structured_answer",
                return_value={"answer": "Approved controls are documented.", "source_ids": ["S1"]},
            ) as ollama,
        ):
            response = client.post(
                "/documents/ask",
                json={"question": "summarise Enterprise_Document_One.pdf", "top_k": 5},
            )
        assert response.status_code == 200
        assert response.json()["sources"][0]["document_id"] == 11
        assert retrieval.call_args.kwargs["document_ids"] == (11,)
        assert response.json()["model"] == KRUTRIM_MODEL
        ollama.assert_called_once()

        with patch("app.services.rag_service.generate_local_structured_answer") as ollama:
            response = client.post(
                "/documents/ask",
                json={"question": "summary of Restricted Secret document"},
            )
        assert response.status_code == 200
        assert response.json()["insufficient_evidence"] is True
        assert response.json()["sources"] == []
        ollama.assert_not_called()
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_ambiguous_named_document_api_requires_clarification_without_ollama(stage11_db):
    _add_document(
        stage11_db,
        document_id=13,
        filename="Enterprise-Document-One.pdf",
        team=stage11_db.get(Team, 1),
        uploader=stage11_db.get(User, 1),
        classification=stage11_db.get(Classification, 1),
        text="A second enterprise document.",
    )
    stage11_db.commit()

    def override_db():
        yield stage11_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=1)
    client = TestClient(app)
    try:
        with patch("app.services.rag_service.generate_local_structured_answer") as ollama:
            response = client.post(
                "/documents/ask",
                json={"question": "summary of enterprise document one"},
            )
        assert response.status_code == 200
        assert response.json()["insufficient_evidence"] is True
        assert response.json()["sources"] == []
        assert "clarify" in response.json()["answer"].casefold()
        ollama.assert_not_called()
    finally:
        client.close()
        app.dependency_overrides.clear()

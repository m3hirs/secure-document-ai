from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

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
from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.main import app
from app.services.entity_presence_service import (
    detect_entity_presence_question,
    detect_entity_count_question,
    detect_named_target_question,
    normalize_literal,
)
from app.services.rag_service import INSUFFICIENT_EVIDENCE_ANSWER, answer_question, classify_rag_intent
from app.services.semantic_search_service import SearchResult


AUTHORIZED_DOCUMENT_ID = 31
RESTRICTED_DOCUMENT_ID = 35


@pytest.fixture
def entity_db():
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
        authorized_user = User(
            id=1,
            name="Authorized User",
            email="authorized@example.test",
            teams=[software],
        )
        restricted_user = User(
            id=2,
            name="Restricted User",
            email="restricted@example.test",
            teams=[design],
        )
        classification = Classification(id=1, name="Internal")
        now = datetime.now(timezone.utc)
        authorized_document = Document(
            id=AUTHORIZED_DOCUMENT_ID,
            filename="Resume.pdf",
            file_path="tests/authorized-resume.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=authorized_user,
            uploaded_at=now,
            teams=[software],
            processing_status="processed",
        )
        restricted_document = Document(
            id=RESTRICTED_DOCUMENT_ID,
            filename="Restricted.pdf",
            file_path="tests/restricted.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=classification,
            uploader=restricted_user,
            uploaded_at=now,
            teams=[design],
            processing_status="processed",
        )
        authorized_page = DocumentPage(
            id=311,
            document=authorized_document,
            page_number=1,
            extracted_text="Candidate: Mihir Shetiya",
            has_text=True,
        )
        restricted_page = DocumentPage(
            id=351,
            document=restricted_document,
            page_number=1,
            extracted_text="Candidate: Aarav Mehta",
            has_text=True,
        )
        db.add_all(
            [
                authorized_document,
                restricted_document,
                DocumentChunk(
                    id=3111,
                    document=authorized_document,
                    page=authorized_page,
                    chunk_index=0,
                    text="Candidate: Mihir Shetiya",
                    character_count=24,
                    source_start_char=0,
                    source_end_char=24,
                ),
                DocumentChunk(
                    id=3511,
                    document=restricted_document,
                    page=restricted_page,
                    chunk_index=0,
                    text="Candidate: Aarav Mehta",
                    character_count=22,
                    source_start_char=0,
                    source_end_char=22,
                ),
            ]
        )
        db.commit()
        yield db
    engine.dispose()


def _set_authorized_text(db: Session, text: str, *, has_text: bool = True) -> None:
    page = db.scalar(select(DocumentPage).where(DocumentPage.id == 311))
    chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.id == 3111))
    assert page is not None and chunk is not None
    page.extracted_text = text
    page.has_text = has_text
    chunk.text = text
    chunk.character_count = len(text)
    chunk.source_end_char = len(text)
    db.commit()


def _add_document(
    db: Session,
    document_id: int,
    text: str,
    *,
    team_id: int | None = 1,
) -> None:
    uploader = db.get(User, 1 if team_id != 2 else 2)
    classification = db.get(Classification, 1)
    teams = [db.get(Team, team_id)] if team_id is not None else []
    document = Document(
        id=document_id,
        filename=f"resume-{document_id}.pdf",
        file_path=f"tests/resume-{document_id}.pdf",
        file_type="application/pdf",
        file_size=100,
        page_count=1,
        classification=classification,
        uploader=uploader,
        uploaded_at=datetime.now(timezone.utc),
        teams=teams,
        processing_status="processed",
    )
    page = DocumentPage(
        id=document_id * 10 + 1,
        document=document,
        page_number=1,
        extracted_text=text,
        has_text=True,
    )
    db.add(
        DocumentChunk(
            id=document_id * 100 + 1,
            document=document,
            page=page,
            chunk_index=0,
            text=text,
            character_count=len(text),
            source_start_char=0,
            source_end_char=len(text),
        )
    )
    db.commit()


def _add_incomplete_authorized_document(db: Session, document_id: int = 40) -> None:
    db.add(
        Document(
            id=document_id,
            filename=f"pending-{document_id}.pdf",
            file_path=f"tests/pending-{document_id}.pdf",
            file_type="application/pdf",
            file_size=100,
            page_count=1,
            classification=db.get(Classification, 1),
            uploader=db.get(User, 1),
            uploaded_at=datetime.now(timezone.utc),
            teams=[db.get(Team, 1)],
            processing_status="uploaded",
        )
    )
    db.commit()


def _post_count_question(db: Session, question: str):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=1)
    client = TestClient(app)
    try:
        with (
            patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
            patch("app.services.rag_service.generate_local_structured_answer") as llm,
        ):
            response = client.post("/documents/ask", json={"question": question, "top_k": 5})
        semantic.assert_not_called()
        llm.assert_not_called()
        return response
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_absent_aarav_mehta_cannot_be_reported_present(entity_db):
    with (
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
        patch("app.services.rag_service.semantic_search") as semantic,
    ):
        result = answer_question(
            entity_db,
            1,
            "Is there any resume named Aarav Mehta?",
        )

    assert result.answer == "No accessible document contains the exact text 'Aarav Mehta'."
    assert not result.answer.casefold().startswith("yes")
    assert result.sources == []
    assert result.insufficient_evidence is False
    llm.assert_not_called()
    semantic.assert_not_called()


def test_present_entity_returns_yes_with_only_literal_supporting_source(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta\nSkills: Python")
    result = answer_question(entity_db, 1, "Is there any PDF containing Aarav Mehta?")

    assert result.answer == "Yes. An accessible document contains the exact text 'Aarav Mehta'."
    assert result.insufficient_evidence is False
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]
    assert all("aarav mehta" in normalize_literal(source.snippet) for source in result.sources)


@pytest.mark.parametrize(
    "evidence",
    [
        "Candidate: AARAV MEHTA",
        "Candidate: Aarav\n\t   Mehta",
    ],
)
def test_entity_match_is_case_insensitive_and_whitespace_normalized(entity_db, evidence):
    _set_authorized_text(entity_db, evidence)
    result = answer_question(entity_db, 1, "Does any document contain Aarav Mehta?")
    assert result.answer.startswith("Yes.")
    assert len(result.sources) == 1


def test_restricted_entity_never_proves_presence_or_leaks_source(entity_db):
    result = answer_question(entity_db, 1, "Find a document containing Aarav Mehta")
    assert result.answer.startswith("No accessible document")
    assert result.sources == []
    assert str(RESTRICTED_DOCUMENT_ID) not in result.answer


def test_semantic_similarity_without_literal_never_calls_semantic_or_llm(entity_db):
    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic_retrieval,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "Is Aarav Mehta mentioned in any accessible document?")
    assert result.answer.startswith("No accessible document")
    semantic_retrieval.assert_not_called()
    llm.assert_not_called()


def test_positive_sources_each_contain_entity_and_restricted_id_is_absent(entity_db):
    _set_authorized_text(entity_db, "Project Falcon delivery notes")
    result = answer_question(entity_db, 1, "Do we have a document containing Project Falcon?")
    assert result.answer.startswith("Yes.")
    assert result.sources
    assert all("project falcon" in normalize_literal(source.snippet) for source in result.sources)
    assert RESTRICTED_DOCUMENT_ID not in {source.document_id for source in result.sources}


def test_incomplete_extraction_returns_insufficient_evidence_instead_of_no(entity_db):
    _set_authorized_text(entity_db, "", has_text=False)
    result = answer_question(entity_db, 1, "Is there any PDF with Aarav Mehta?")
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True


def test_page_match_without_matching_chunk_fails_closed(entity_db):
    page = entity_db.scalar(select(DocumentPage).where(DocumentPage.id == 311))
    assert page is not None
    page.extracted_text = "Candidate: Aarav Mehta"
    entity_db.commit()
    result = answer_question(entity_db, 1, "Is there any PDF containing Aarav Mehta?")
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True


@pytest.mark.parametrize(
    ("question", "entity"),
    [
        ("Is there any document containing John Smith?", "John Smith"),
        ("is there any pdf with named aarav mehta in it", "aarav mehta"),
        ("Do we have a resume for Project Falcon?", "Project Falcon"),
        ("Is John Smith mentioned in any accessible document?", "John Smith"),
        ("Does any document contain Project Falcon?", "Project Falcon"),
        ("Find a document containing Aarav Mehta", "Aarav Mehta"),
    ],
)
def test_presence_question_detection_is_conservative_and_extracts_literal(question, entity):
    intent = detect_entity_presence_question(question)
    assert intent is not None
    assert intent.entity == entity


@pytest.mark.parametrize(
    "question",
    [
        "What programming languages are listed?",
        "Summarize the resume.",
        "What is Project Falcon?",
        "Which documents discuss monitoring?",
    ],
)
def test_ordinary_rag_questions_do_not_enter_entity_presence_path(question):
    assert detect_entity_presence_question(question) is None


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("How many PDFs contain Project Falcon?", "entity_count"),
        ("Is there any PDF containing Project Falcon?", "entity_presence"),
        ("What technologies are listed in Project Falcon resume?", "named_document"),
        ("Which programming languages are listed?", "category"),
        ("Explain the monitoring architecture", "general"),
    ],
)
def test_rag_intent_router_uses_required_precedence(question, kind):
    assert classify_rag_intent(question).kind == kind


@pytest.mark.parametrize(
    ("question", "entity", "kind"),
    [
        ("how many PDFs contain Aarav Mehta", "Aarav Mehta", "PDF"),
        ("how many pdf has aarav mehta name in it", "aarav mehta", "PDF"),
        ("how many documents have Aarav Mehta", "Aarav Mehta", "document"),
        ("number of resumes containing Aarav Mehta", "Aarav Mehta", "resume"),
        ("count documents with Aarav Mehta", "Aarav Mehta", "document"),
    ],
)
def test_entity_count_question_detection(question, entity, kind):
    intent = detect_entity_count_question(question)
    assert intent is not None
    assert intent.entity == entity
    assert intent.document_kind == kind


@pytest.mark.parametrize(
    ("question", "entity", "kind"),
    [
        ("How many PDFs contain Aarav Mehta?", "Aarav Mehta", "PDF"),
        ("how many pdf has mihir shetiya name in it", "mihir shetiya", "PDF"),
        ("count documents with Priya Sharma", "Priya Sharma", "document"),
        ("number of resumes containing Project Falcon", "Project Falcon", "resume"),
    ],
)
def test_entity_count_detection_is_entity_agnostic(question, entity, kind):
    intent = detect_entity_count_question(question)

    assert intent is not None
    assert intent.entity == entity
    assert intent.document_kind == kind


@pytest.mark.parametrize("punctuation", ["?", "!", ".", ",", ":", ";"])
def test_entity_count_detection_strips_terminal_query_punctuation(punctuation):
    intent = detect_entity_count_question(
        f"How many PDFs contain Aarav Mehta{punctuation}"
    )

    assert intent is not None
    assert intent.entity == "Aarav Mehta"
    assert intent.document_kind == "PDF"


def test_punctuated_count_query_is_deterministic_and_does_not_use_rag(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta\nSkills: Python")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "How many PDFs contain Aarav Mehta?")

    assert result.answer == "1 accessible PDF contains the exact text 'Aarav Mehta'."
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]
    semantic.assert_not_called()
    llm.assert_not_called()


@pytest.mark.parametrize(
    ("entity", "question", "expected_answer"),
    [
        (
            "Aarav Mehta",
            "How many PDFs contain Aarav Mehta?",
            "1 accessible PDF contains the exact text 'Aarav Mehta'.",
        ),
        (
            "Mihir Shetiya",
            "count documents with Mihir Shetiya",
            "1 accessible document contains the exact text 'Mihir Shetiya'.",
        ),
        (
            "Priya Sharma",
            "number of resumes containing Priya Sharma!",
            "1 accessible resume contains the exact text 'Priya Sharma'.",
        ),
        (
            "Project Falcon",
            "how many pdf has Project Falcon name in it;",
            "1 accessible PDF contains the exact text 'Project Falcon'.",
        ),
    ],
)
def test_deterministic_count_is_entity_agnostic(
    entity_db,
    entity,
    question,
    expected_answer,
):
    _set_authorized_text(entity_db, f"Record: {entity}\nVerified content")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, question)

    assert result.answer == expected_answer
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]
    assert all(normalize_literal(entity) in normalize_literal(source.snippet) for source in result.sources)
    semantic.assert_not_called()
    llm.assert_not_called()


@pytest.mark.parametrize(
    ("question", "entity", "expected_answer"),
    [
        ("How many PDFs contain Aarav Mehta?", "Aarav Mehta", "1 accessible PDF contains the exact text 'Aarav Mehta'."),
        ("How many PDFs contain Mihir Shetiya?", "Mihir Shetiya", "1 accessible PDF contains the exact text 'Mihir Shetiya'."),
        ("count documents with Aarav Mehta", "Aarav Mehta", "1 accessible document contains the exact text 'Aarav Mehta'."),
        ("number of resumes containing Aarav Mehta", "Aarav Mehta", "1 accessible resume contains the exact text 'Aarav Mehta'."),
        ("how many pdf has Aarav Mehta name in it", "Aarav Mehta", "1 accessible PDF contains the exact text 'Aarav Mehta'."),
        ("How many PDFs contain Project Falcon?", "Project Falcon", "1 accessible PDF contains the exact text 'Project Falcon'."),
    ],
)
def test_documents_ask_api_dispatches_count_before_rag(entity_db, question, entity, expected_answer):
    _set_authorized_text(entity_db, f"Record: {entity}")

    def override_db():
        yield entity_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=1)
    client = TestClient(app)
    try:
        with (
            patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
            patch("app.services.rag_service.generate_local_structured_answer") as llm,
        ):
            response = client.post("/documents/ask", json={"question": question, "top_k": 5})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == expected_answer
        assert [source["document_id"] for source in payload["sources"]] == [AUTHORIZED_DOCUMENT_ID]
        assert RESTRICTED_DOCUMENT_ID not in {source["document_id"] for source in payload["sources"]}
        semantic.assert_not_called()
        llm.assert_not_called()
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_documents_ask_api_count_excludes_archived_match_without_rag(entity_db):
    _set_authorized_text(entity_db, "Record: Project Falcon")
    entity_db.add(UserDocumentPreference(user_id=1, document_id=AUTHORIZED_DOCUMENT_ID, is_archived=True, archived_at=datetime.now(timezone.utc)))
    entity_db.commit()

    def override_db():
        yield entity_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=1)
    client = TestClient(app)
    try:
        with (
            patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
            patch("app.services.rag_service.generate_local_structured_answer") as llm,
        ):
            response = client.post("/documents/ask", json={"question": "How many PDFs contain Project Falcon?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "No active accessible PDF contains the exact text 'Project Falcon'."
        assert response.json()["sources"] == []
        semantic.assert_not_called()
        llm.assert_not_called()
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_api_incomplete_corpus_returns_partial_count_with_verified_source(entity_db):
    _set_authorized_text(entity_db, "Record: Project Falcon")
    _add_incomplete_authorized_document(entity_db)

    response = _post_count_question(entity_db, "How many PDFs contain Project Falcon?")

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "I found 1 verified accessible PDF containing the exact text 'Project Falcon', "
        "but I cannot determine the complete count because some accessible documents "
        "have not been fully processed."
    )
    assert response.json()["insufficient_evidence"] is True
    assert [source["document_id"] for source in response.json()["sources"]] == [AUTHORIZED_DOCUMENT_ID]


def test_api_incomplete_corpus_returns_uncertain_no_match(entity_db):
    _set_authorized_text(entity_db, "Record: unrelated material")
    _add_incomplete_authorized_document(entity_db)

    response = _post_count_question(entity_db, "Count documents with Priya Sharma")

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "I found no verified match for 'Priya Sharma' in the fully processed accessible "
        "documents, but I cannot determine the complete count because some accessible "
        "documents have not been fully processed."
    )
    assert response.json()["insufficient_evidence"] is True
    assert response.json()["sources"] == []


def test_api_incomplete_corpus_reports_multiple_verified_matches(entity_db):
    _set_authorized_text(entity_db, "Record: Project Falcon")
    _add_document(entity_db, 32, "Project Falcon delivery record")
    _add_incomplete_authorized_document(entity_db)

    response = _post_count_question(entity_db, "How many PDFs contain Project Falcon?")

    assert response.status_code == 200
    assert response.json()["answer"].startswith(
        "I found 2 verified accessible PDFs containing the exact text 'Project Falcon'"
    )
    assert response.json()["insufficient_evidence"] is True
    assert {source["document_id"] for source in response.json()["sources"]} == {AUTHORIZED_DOCUMENT_ID, 32}


def test_api_unauthorized_match_is_excluded_from_exact_count(entity_db):
    _set_authorized_text(entity_db, "Record: unrelated material")

    response = _post_count_question(entity_db, "How many PDFs contain Aarav Mehta?")

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "No active accessible PDF contains the exact text 'Aarav Mehta'."
    )
    assert response.json()["sources"] == []


def test_count_excludes_semantically_related_mihir_resume_and_restricted_document(entity_db):
    _add_document(entity_db, 32, "Candidate: Aarav Mehta\nSkills: Python")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "how many pdf has aarav mehta name in it")

    assert result.answer == "1 accessible PDF contains the exact text 'Aarav Mehta'."
    assert result.insufficient_evidence is False
    assert [source.document_id for source in result.sources] == [32]
    assert all("aarav mehta" in normalize_literal(source.snippet) for source in result.sources)
    assert AUTHORIZED_DOCUMENT_ID not in {source.document_id for source in result.sources}
    assert RESTRICTED_DOCUMENT_ID not in {source.document_id for source in result.sources}
    semantic.assert_not_called()
    llm.assert_not_called()


def test_multiple_matching_chunks_in_one_pdf_count_once(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta")
    page = entity_db.get(DocumentPage, 311)
    document = entity_db.get(Document, AUTHORIZED_DOCUMENT_ID)
    entity_db.add(
        DocumentChunk(
            id=3112,
            document=document,
            page=page,
            chunk_index=1,
            text="Aarav Mehta experience",
            character_count=22,
            source_start_char=24,
            source_end_char=46,
        )
    )
    entity_db.commit()

    result = answer_question(entity_db, 1, "How many PDFs contain Aarav Mehta?")
    assert result.answer.startswith("1 accessible PDF contains")
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]


def test_two_authorized_matching_pdfs_count_as_two_distinct_documents(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta")
    _add_document(entity_db, 32, "Profile for AARAV   MEHTA")
    result = answer_question(entity_db, 1, "How many PDFs contain Aarav Mehta?")
    assert result.answer == "2 accessible PDFs contain the exact text 'Aarav Mehta'."
    assert {source.document_id for source in result.sources} == {AUTHORIZED_DOCUMENT_ID, 32}


def test_unassigned_and_unauthorized_matching_pdfs_are_not_counted(entity_db):
    _add_document(entity_db, 32, "Candidate: Aarav Mehta", team_id=None)
    # The fixture's Design-only document 35 also contains the name.
    result = answer_question(entity_db, 1, "How many PDFs contain Aarav Mehta?")
    assert result.answer == "No active accessible PDF contains the exact text 'Aarav Mehta'."
    assert result.sources == []


def test_archived_matching_pdf_is_excluded_from_active_workspace_count(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta")
    entity_db.add(
        UserDocumentPreference(
            user_id=1,
            document_id=AUTHORIZED_DOCUMENT_ID,
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
        )
    )
    entity_db.commit()
    result = answer_question(entity_db, 1, "How many PDFs contain Aarav Mehta?")
    assert result.answer == "No active accessible PDF contains the exact text 'Aarav Mehta'."
    assert result.sources == []


@pytest.mark.parametrize(
    "entity",
    ["Aarav Mehta", "Mihir Shetiya", "Priya Sharma", "Project Falcon"],
)
def test_archived_entity_is_generically_excluded_from_active_count(entity_db, entity):
    _set_authorized_text(entity_db, f"Record: {entity}")
    entity_db.add(
        UserDocumentPreference(
            user_id=1,
            document_id=AUTHORIZED_DOCUMENT_ID,
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
        )
    )
    entity_db.commit()

    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, f"How many documents contain {entity}?")

    assert result.answer == f"No active accessible document contains the exact text '{entity}'."
    assert result.sources == []
    semantic.assert_not_called()
    llm.assert_not_called()


def test_archived_matching_pdf_is_excluded_from_entity_presence(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta")
    entity_db.add(
        UserDocumentPreference(
            user_id=1,
            document_id=AUTHORIZED_DOCUMENT_ID,
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
        )
    )
    entity_db.commit()
    result = answer_question(entity_db, 1, "Is there any PDF containing Aarav Mehta?")
    assert result.answer == "No accessible document contains the exact text 'Aarav Mehta'."
    assert result.sources == []


def test_no_matching_document_returns_deterministic_zero_without_llm(entity_db):
    with (
        patch("app.services.rag_service.retrieve_authorized_passages") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "Count documents with Aarav Mehta")
    assert result.answer == "No active accessible document contains the exact text 'Aarav Mehta'."
    assert result.sources == []
    assert result.insufficient_evidence is False
    semantic.assert_not_called()
    llm.assert_not_called()


@pytest.mark.parametrize(
    "question",
    [
        "summarize Aarav Mehta resume",
        "give me summary of Aarav Mehta's resume",
        "what technologies are in Aarav Mehta resume",
        "tell me about Aarav Mehta resume",
        "skills in Aarav Mehta PDF",
        "experience of Aarav Mehta",
        "projects in Aarav Mehta resume",
    ],
)
def test_named_target_detection_extracts_conservative_literal(question):
    intent = detect_named_target_question(question)
    assert intent is not None
    assert intent.entity == "Aarav Mehta"


@pytest.mark.parametrize(
    "question",
    [
        "summarize my resume",
        "tell me about the resume",
        "what technologies are in this document",
        "summarize the accessible documents",
    ],
)
def test_generic_document_questions_are_not_bound_to_a_named_target(question):
    assert detect_named_target_question(question) is None


def _named_semantic_result(document_id: int, text: str) -> SearchResult:
    return SearchResult(
        document_id=document_id,
        filename=f"resume-{document_id}.pdf",
        page_number=1,
        chunk_id=document_id * 100 + 1,
        chunk_text=text,
        similarity_score=0.91,
    )


def test_active_named_target_restricts_rag_to_resolved_document(entity_db):
    _set_authorized_text(entity_db, "Aarav Mehta\nSkills: Python and FastAPI")
    unrelated = _named_semantic_result(999, "Unrelated resume content")
    matching = _named_semantic_result(AUTHORIZED_DOCUMENT_ID, "Aarav Mehta uses Python")
    with (
        patch(
            "app.services.rag_service.semantic_search",
            return_value=[unrelated, matching],
        ) as semantic,
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "A supported summary.", "source_ids": ["S1"]},
        ) as llm,
    ):
        result = answer_question(entity_db, 1, "Summarize Aarav Mehta resume")

    assert result.insufficient_evidence is False
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]
    assert semantic.call_args.kwargs["document_ids"] == (AUTHORIZED_DOCUMENT_ID,)
    assert "Unrelated resume content" not in llm.call_args.args[1]


def test_archived_named_target_fails_before_semantic_search_or_ollama(entity_db):
    _set_authorized_text(entity_db, "Candidate: Aarav Mehta")
    entity_db.add(
        UserDocumentPreference(
            user_id=1,
            document_id=AUTHORIZED_DOCUMENT_ID,
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
        )
    )
    entity_db.commit()
    with (
        patch("app.services.rag_service.semantic_search") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "Summarize Aarav Mehta resume")
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    semantic.assert_not_called()
    llm.assert_not_called()


def test_named_target_only_in_unauthorized_document_does_not_leak_existence(entity_db):
    with (
        patch("app.services.rag_service.semantic_search") as semantic,
        patch("app.services.rag_service.generate_local_structured_answer") as llm,
    ):
        result = answer_question(entity_db, 1, "Tell me about Aarav Mehta resume")
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    semantic.assert_not_called()
    llm.assert_not_called()


def test_restored_named_target_becomes_eligible_again(entity_db):
    _set_authorized_text(entity_db, "Aarav Mehta\nTechnologies: Python")
    preference = UserDocumentPreference(
        user_id=1,
        document_id=AUTHORIZED_DOCUMENT_ID,
        is_archived=True,
        archived_at=datetime.now(timezone.utc),
    )
    entity_db.add(preference)
    entity_db.commit()
    assert answer_question(entity_db, 1, "Summarize Aarav Mehta resume").insufficient_evidence is True

    preference.is_archived = False
    preference.archived_at = None
    entity_db.commit()
    with (
        patch(
            "app.services.rag_service.semantic_search",
            return_value=[_named_semantic_result(AUTHORIZED_DOCUMENT_ID, "Aarav Mehta Technologies: Python")],
        ),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Python is listed.", "source_ids": ["S1"]},
        ),
    ):
        result = answer_question(entity_db, 1, "What technologies are in Aarav Mehta resume?")
    assert result.insufficient_evidence is False
    assert [source.document_id for source in result.sources] == [AUTHORIZED_DOCUMENT_ID]

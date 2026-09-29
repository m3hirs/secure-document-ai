from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.main import app
from app.services.llm_service import LocalLLMError
from app.services.rag_service import INSUFFICIENT_EVIDENCE_ANSWER


QUESTION = "What local processing control is required?"
CONFIGURED_MODEL = "hf.co/bartowski/krutrim-ai-labs_Krutrim-2-instruct-GGUF:Q4_K_M"


def _answer() -> dict:
    return {
        "answer": "Local processing is required [S1].",
        "sources": [
            {
                "source_id": "S1",
                "document_id": 7,
                "filename": "authorized.pdf",
                "page_number": 2,
                "chunk_id": 11,
                "snippet": "Local processing is required.",
                "similarity": 0.9,
            }
        ],
        "model": CONFIGURED_MODEL,
        "insufficient_evidence": False,
    }


def _fake_db():
    yield object()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=42)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_ask_documents_returns_answer_and_forwards_trusted_identity_and_payload(client):
    with patch("app.api.rag.answer_question", return_value=_answer()) as answer_question:
        response = client.post(
            "/documents/ask",
            json={"question": QUESTION, "top_k": 3},
        )

    assert response.status_code == 200
    assert response.json() == _answer()
    answer_question.assert_called_once_with(
        db=answer_question.call_args.kwargs["db"],
        user_id=42,
        question=QUESTION,
        top_k=3,
    )


def test_ask_documents_uses_default_top_k(client):
    with patch("app.api.rag.answer_question", return_value=_answer()) as answer_question:
        response = client.post("/documents/ask", json={"question": QUESTION})

    assert response.status_code == 200
    assert answer_question.call_args.kwargs["user_id"] == 42
    assert answer_question.call_args.kwargs["question"] == QUESTION
    assert answer_question.call_args.kwargs["top_k"] == 5


def test_client_supplied_user_id_is_rejected(client):
    response = client.post(
        "/documents/ask",
        json={"question": QUESTION, "user_id": 999},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("question", ["", " \t\n"])
def test_empty_or_whitespace_question_is_rejected(client, question: str):
    response = client.post("/documents/ask", json={"question": question})

    assert response.status_code == 422


@pytest.mark.parametrize("top_k", [0, 11])
def test_invalid_top_k_is_rejected(client, top_k: int):
    response = client.post(
        "/documents/ask",
        json={"question": QUESTION, "top_k": top_k},
    )

    assert response.status_code == 422


def test_local_llm_error_is_sanitized(client):
    with patch(
        "app.api.rag.answer_question",
        side_effect=LocalLLMError("Ollama http://127.0.0.1:11434 failed"),
    ):
        response = client.post("/documents/ask", json={"question": QUESTION})

    assert response.status_code == 503
    assert response.json() == {"detail": "Local AI service is temporarily unavailable."}
    assert "127.0.0.1" not in response.text
    assert "Ollama" not in response.text


def test_missing_or_invalid_trusted_identity_fails_closed():
    app.dependency_overrides[get_db] = _fake_db
    try:
        with TestClient(app) as client:
            response = client.post("/documents/ask", json={"question": QUESTION})

        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}
    finally:
        app.dependency_overrides.clear()


def test_insufficient_evidence_result_is_returned_as_success(client):
    insufficient_result = {
        "answer": INSUFFICIENT_EVIDENCE_ANSWER,
        "sources": [],
        "model": CONFIGURED_MODEL,
        "insufficient_evidence": True,
    }
    with patch("app.api.rag.answer_question", return_value=insufficient_result):
        response = client.post("/documents/ask", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == insufficient_result

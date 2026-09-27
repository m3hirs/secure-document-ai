from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.main import app
from app.services.entity_presence_service import NamedTargetResolution
from app.services.semantic_search_service import SearchResult, has_lexical_relevance


def _fake_db():
    yield object()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=7)
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()


def _result(document_id=31):
    return SearchResult(document_id, "authorized.pdf", 1, 91, "Aarav Mehta profile", 0.84)


def test_named_semantic_search_is_scoped_to_resolved_active_document(client):
    with (
        patch("app.api.search.resolve_authorized_named_target", return_value=NamedTargetResolution((31,), True)),
        patch("app.api.search.semantic_search", return_value=[_result()]) as search,
    ):
        response = client.post("/search/semantic", json={"query": "Aarav Mehta resume", "top_k": 5})
    assert response.status_code == 200
    assert [item["document_id"] for item in response.json()["results"]] == [31]
    assert search.call_args.kwargs["document_ids"] == (31,)
    assert search.call_args.args[1] == 7


def test_archived_or_unauthorized_named_target_returns_no_substitute(client):
    with (
        patch("app.api.search.resolve_authorized_named_target", return_value=NamedTargetResolution((), True)),
        patch("app.api.search.semantic_search") as search,
    ):
        response = client.post("/search/semantic", json={"query": "Aarav Mehta resume"})
    assert response.status_code == 200
    assert response.json() == {"results": [], "message": "No relevant documents found."}
    search.assert_not_called()


def test_nonsense_semantic_search_returns_no_relevant_documents(client):
    with patch("app.api.search.semantic_search", return_value=[]):
        response = client.post(
            "/search/semantic",
            json={"query": "quantum banana farming satellite recipe"},
        )
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["message"] == "No relevant documents found."


@pytest.mark.parametrize(
    ("query", "filename", "text", "expected"),
    [
        ("responsible AI monitoring", "risk-platform.pdf", "Responsible AI risk monitoring platform", True),
        ("Aarav Mehta resume", "aarav-mehta.pdf", "Software engineering profile", True),
        ("quantum banana farming satellite recipe", "resume.pdf", "Python and PostgreSQL experience", False),
        ("easy cooking dinner recipe", "resume.pdf", "Machine learning engineer", False),
        ("distant galaxy telescope astronomy", "resume.pdf", "Backend API development", False),
    ],
)
def test_secondary_lexical_relevance_gate(query, filename, text, expected):
    assert has_lexical_relevance(query, filename, text) is expected

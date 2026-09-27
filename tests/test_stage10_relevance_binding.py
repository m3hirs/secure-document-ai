from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.semantic_search_service import (
    semantic_search,
    similarity_meets_threshold,
)


def _row(document_id: int, distance: float):
    embedding = SimpleNamespace()
    chunk = SimpleNamespace(id=document_id * 10, text=f"Evidence {document_id}")
    document = SimpleNamespace(id=document_id, filename=f"document-{document_id}.pdf")
    page = SimpleNamespace(page_number=1)
    return embedding, chunk, document, page, distance


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.699999, False), (0.70, True), (0.700001, True)],
)
def test_similarity_threshold_is_inclusive(score, expected):
    assert similarity_meets_threshold(score, 0.70) is expected


def test_semantic_search_drops_below_threshold_and_keeps_boundary_and_above():
    db = Mock()
    db.execute.return_value.all.return_value = [
        _row(1, 0.31),
        _row(2, 0.30),
        _row(3, 0.29),
    ]
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
        results = semantic_search(db, 7, "relevant evidence", 5)

    assert [result.document_id for result in results] == [2, 3]
    assert [result.similarity_score for result in results] == pytest.approx([0.70, 0.71])
    sql = str(db.execute.call_args.args[0].compile()).casefold()
    assert "user_document_preferences" in sql
    assert "document_teams" in sql


def test_only_below_threshold_candidates_return_no_results():
    db = Mock()
    db.execute.return_value.all.return_value = [_row(1, 0.45), _row(2, 0.31)]
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
        assert semantic_search(db, 7, "unrelated", 5) == []


def test_named_document_scope_is_applied_inside_authorized_semantic_query():
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
        semantic_search(db, 7, "Aarav Mehta resume", 5, document_ids=(31,))

    compiled = db.execute.call_args.args[0].compile()
    sql = str(compiled).casefold()
    assert "documents.id" in sql
    assert "user_document_preferences" in sql
    assert "document_teams" in sql
    assert any(value == [31] or value == (31,) for value in compiled.params.values())


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_invalid_similarity_threshold_is_rejected(threshold):
    with pytest.raises(ValidationError, match="SEMANTIC_SEARCH_MIN_SIMILARITY"):
        Settings(
            _env_file=None,
            database_url="sqlite+pysqlite:///:memory:",
            semantic_search_min_similarity=threshold,
        )

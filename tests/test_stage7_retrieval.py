from unittest.mock import Mock, patch

import pytest

from app.services.rag_service import retrieve_authorized_passages
from app.services.semantic_search_service import SearchResult


def _result(document_id: int, page_number: int, chunk_id: int) -> SearchResult:
    return SearchResult(
        document_id=document_id,
        filename=f"document-{document_id}.pdf",
        page_number=page_number,
        chunk_id=chunk_id,
        chunk_text=f"Authorized passage {chunk_id}",
        similarity_score=0.9,
    )


def test_retrieval_passes_trusted_identity_and_top_k_to_semantic_search():
    db = Mock()

    with patch(
        "app.services.rag_service.semantic_search",
        return_value=[_result(7, 2, 31)],
    ) as search:
        passages = retrieve_authorized_passages(
            db=db,
            user_id=42,
            question="Which controls are required?",
            top_k=3,
        )

    search.assert_called_once_with(
        db=db,
        user_id=42,
        query="Which controls are required?",
        top_k=3,
    )
    assert len(passages) == 1


def test_retrieval_assigns_source_ids_in_semantic_retrieval_order():
    with patch(
        "app.services.rag_service.semantic_search",
        return_value=[_result(7, 2, 31), _result(8, 5, 44)],
    ):
        passages = retrieve_authorized_passages(
            db=Mock(),
            user_id=42,
            question="What is required?",
        )

    assert [passage.source_id for passage in passages] == ["S1", "S2"]
    assert [passage.chunk_id for passage in passages] == [31, 44]


def test_empty_retrieval_returns_no_passages():
    with patch("app.services.rag_service.semantic_search", return_value=[]):
        passages = retrieve_authorized_passages(
            db=Mock(),
            user_id=42,
            question="What is required?",
        )

    assert passages == []


@pytest.mark.parametrize("top_k", [0, 11])
def test_retrieval_rejects_top_k_outside_service_boundary(top_k: int):
    with patch("app.services.rag_service.semantic_search") as search:
        with pytest.raises(ValueError, match="top_k must be between 1 and 10"):
            retrieve_authorized_passages(
                db=Mock(),
                user_id=42,
                question="What is required?",
                top_k=top_k,
            )

    search.assert_not_called()


def test_retrieval_preserves_citation_references_and_never_calls_ollama():
    result = _result(document_id=7, page_number=2, chunk_id=31)

    with (
        patch(
            "app.services.rag_service.semantic_search",
            return_value=[result],
        ),
        patch("app.services.llm_service.generate_local_summary") as ollama,
    ):
        passages = retrieve_authorized_passages(
            db=Mock(),
            user_id=42,
            question="What is required?",
        )

    passage = passages[0]
    assert passage.document_id == 7
    assert passage.filename == "document-7.pdf"
    assert passage.page_number == 2
    assert passage.chunk_id == 31
    assert passage.snippet == "Authorized passage 31"
    assert passage.similarity == 0.9
    ollama.assert_not_called()

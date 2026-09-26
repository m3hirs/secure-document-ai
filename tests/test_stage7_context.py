from unittest.mock import patch

from app.schemas.rag import RagSourceRead
from app.services.rag_service import (
    RAG_CONTEXT_CHARACTER_BUDGET,
    select_rag_context,
)


def _source(source_id: str, chunk_id: int, snippet: str) -> RagSourceRead:
    return RagSourceRead(
        source_id=source_id,
        document_id=7,
        filename="authorized.pdf",
        page_number=2,
        chunk_id=chunk_id,
        snippet=snippet,
        similarity=0.9,
    )


def test_short_passages_fit_and_preserve_retrieval_order():
    passages = [_source("S1", 11, "First passage."), _source("S2", 12, "Second passage.")]

    result = select_rag_context(passages, "What does the document require?")

    assert [source.source_id for source in result.sources] == ["S1", "S2"]
    assert result.context.index("First passage.") < result.context.index("Second passage.")


def test_context_includes_matching_source_ids_and_citation_metadata():
    result = select_rag_context([_source("S1", 11, "Authorized text.")], "Question")

    assert "[Source S1]" in result.context
    assert "Document ID: 7" in result.context
    assert "Page: 2" in result.context
    assert "Chunk ID: 11" in result.context
    assert "--- BEGIN UNTRUSTED PASSAGE ---" in result.context
    assert "--- END UNTRUSTED PASSAGE ---" in result.context


def test_returned_sources_match_only_the_passages_in_context():
    included = _source("S1", 11, "Included text.")
    skipped = _source("S2", 12, " " * 3)

    result = select_rag_context([included, skipped], "Question")

    assert result.sources == [included]
    assert "Included text." in result.context
    assert "S2" not in result.context


def test_long_passages_respect_the_configured_conservative_budget():
    oversized = _source("S1", 11, "A" * (RAG_CONTEXT_CHARACTER_BUDGET + 1))
    fitting = _source("S2", 12, "Short authorized passage.")

    result = select_rag_context([oversized, fitting], "Question")

    assert len(result.context) + len("Question") <= RAG_CONTEXT_CHARACTER_BUDGET
    assert [source.source_id for source in result.sources] == ["S2"]


def test_long_question_reduces_available_passage_capacity():
    passage = _source("S1", 11, "A" * 7000)

    short_question_result = select_rag_context([passage], "Q")
    long_question_result = select_rag_context([passage], "Q" * 1000)

    assert short_question_result.sources == [passage]
    assert long_question_result.context == ""
    assert long_question_result.sources == []


def test_empty_passages_return_no_context_or_sources():
    result = select_rag_context([], "Question")

    assert result.context == ""
    assert result.sources == []


def test_original_passages_are_not_mutated():
    passage = _source("S1", 11, "Original text.")
    original = passage.model_dump()

    result = select_rag_context([passage], "Question")

    assert passage.model_dump() == original
    assert result.sources[0] is not passage


def test_source_ids_remain_consistent_after_an_oversized_passage_is_skipped():
    oversized = _source("S1", 11, "A" * (RAG_CONTEXT_CHARACTER_BUDGET + 1))
    later = _source("S2", 12, "Later authorized text.")

    result = select_rag_context([oversized, later], "Question")

    assert [source.source_id for source in result.sources] == ["S2"]
    assert "[Source S2]" in result.context
    assert "[Source S1]" not in result.context


def test_context_selection_never_invokes_ollama_or_a_database():
    with patch("app.services.llm_service.generate_local_summary") as ollama:
        result = select_rag_context([_source("S1", 11, "Local text.")], "Question")

    assert result.sources
    ollama.assert_not_called()

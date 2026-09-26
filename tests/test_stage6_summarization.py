from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.services.summarization_service import (
    MAX_SUMMARY_CHARACTERS,
    select_summary_text,
    summarize_document,
)


def test_unauthorized_document_never_reaches_llm():
    db = Mock()

    with (
        patch(
            "app.services.summarization_service.accessible_document",
            return_value=None,
        ) as mock_access,
        patch(
            "app.services.summarization_service.generate_local_summary"
        ) as mock_llm,
    ):
        with pytest.raises(HTTPException) as exc:
            summarize_document(
                db=db,
                document_id=35,
                user_id=1,
            )

    assert exc.value.status_code == 404
    mock_access.assert_called_once_with(db, 35, 1)

    # No document-page query and no LLM call.
    db.scalars.assert_not_called()
    mock_llm.assert_not_called()


def test_authorized_document_can_be_summarized():
    db = Mock()

    document = SimpleNamespace(
        id=31,
        filename="sample.pdf",
    )

    page = SimpleNamespace(
        extracted_text="This document describes a local AI system."
    )

    db.scalars.return_value.all.return_value = [page]

    with (
        patch(
            "app.services.summarization_service.accessible_document",
            return_value=document,
        ),
        patch(
            "app.services.summarization_service.generate_local_summary",
            return_value="- A local AI system is described.",
        ) as mock_llm,
    ):
        result = summarize_document(
            db=db,
            document_id=31,
            user_id=1,
        )

    mock_llm.assert_called_once_with(
        "This document describes a local AI system."
    )

    assert result["document_id"] == 31
    assert result["filename"] == "sample.pdf"
    assert result["summary"] == "- A local AI system is described."
    assert result["truncated"] is False


def test_document_without_text_is_rejected():
    db = Mock()

    document = SimpleNamespace(
        id=31,
        filename="empty.pdf",
    )

    page = SimpleNamespace(extracted_text="   ")

    db.scalars.return_value.all.return_value = [page]

    with (
        patch(
            "app.services.summarization_service.accessible_document",
            return_value=document,
        ),
        patch(
            "app.services.summarization_service.generate_local_summary"
        ) as mock_llm,
    ):
        with pytest.raises(HTTPException) as exc:
            summarize_document(
                db=db,
                document_id=31,
                user_id=1,
            )

    assert exc.value.status_code == 422
    mock_llm.assert_not_called()

def test_short_document_is_not_truncated():
    original = "This is a short document about machine learning."

    selected, truncated = select_summary_text(original)

    assert selected == original
    assert truncated is False


def test_long_document_includes_beginning_middle_and_end():
    original = (
        "BEGINNING " + "A" * 10000
        + " MIDDLE " + "B" * 10000
        + " ENDING"
    )

    selected, truncated = select_summary_text(original)

    assert truncated is True
    assert len(selected) <= MAX_SUMMARY_CHARACTERS

    assert "BEGINNING" in selected
    assert "MIDDLE" in selected
    assert "ENDING" in selected

    assert "[... document section omitted ...]" in selected


def test_document_at_character_limit_is_not_truncated():
    original = "A" * MAX_SUMMARY_CHARACTERS

    selected, truncated = select_summary_text(original)

    assert selected == original
    assert truncated is False


def test_document_one_character_over_budget_is_truncated():
    original = "A" * (MAX_SUMMARY_CHARACTERS + 1)
    selected, truncated = select_summary_text(original)
    assert truncated is True
    assert len(selected) <= MAX_SUMMARY_CHARACTERS

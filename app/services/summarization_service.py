"""Authorization-first document summarization."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentPage
from app.services.llm_service import (
    MAX_SUMMARY_INPUT_CHARACTERS,
    generate_local_summary,
    get_ollama_model_name,
)
from app.services.semantic_search_service import accessible_document


MAX_SUMMARY_CHARACTERS = MAX_SUMMARY_INPUT_CHARACTERS
OMITTED_SECTION_MARKER = "\n\n[... document section omitted ...]\n\n"


def select_summary_text(document_text: str) -> tuple[str, bool]:
    """Keep representative beginning, middle, and ending text within the LLM limit."""
    if len(document_text) <= MAX_SUMMARY_CHARACTERS:
        return document_text, False

    available = MAX_SUMMARY_CHARACTERS - 2 * len(OMITTED_SECTION_MARKER)
    beginning_size = available // 3
    middle_size = available // 3
    ending_size = available - beginning_size - middle_size
    middle_start = max(0, len(document_text) // 2 - middle_size // 2)

    selected = (
        document_text[:beginning_size]
        + OMITTED_SECTION_MARKER
        + document_text[middle_start:middle_start + middle_size]
        + OMITTED_SECTION_MARKER
        + document_text[-ending_size:]
    )
    return selected, True


def summarize_document(
    db: Session,
    document_id: int,
    user_id: int,
) -> dict:
    """Summarize a directly requested document after team authorization.

    This is a direct-by-ID action, like document detail, rather than workspace
    retrieval. Per-user archive state therefore does not grant or revoke this
    operation; SQL team authorization remains authoritative.
    """

    # SECURITY: Check permission before retrieving document text.
    document = accessible_document(db, document_id, user_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).all()

    text_parts = [
        page.extracted_text.strip()
        for page in pages
        if page.extracted_text and page.extracted_text.strip()
    ]

    if not text_parts:
        raise HTTPException(
            status_code=422,
            detail="Document has no extracted text to summarize",
        )

    document_text = "\n\n".join(text_parts)

    document_text, truncated = select_summary_text(document_text)

    summary = generate_local_summary(document_text)

    return {
        "document_id": document.id,
        "filename": document.filename,
        "summary": summary,
        "model": get_ollama_model_name(),
        "source_characters": len(document_text),
        "truncated": truncated,
    }

"""Authorization-aware metadata and hybrid document search."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, document_tags, document_teams
from app.services.natural_search_parser import ParsedSearch
from app.services.semantic_search_service import (
    document_active_workspace_clause,
    hybrid_search,
)


def _filters(parsed: ParsedSearch):
    clauses = []
    if parsed.file_type:
        clauses.append(Document.file_type == parsed.file_type)
    if parsed.uploader_id:
        clauses.append(Document.uploaded_by == parsed.uploader_id)
    if parsed.team_id:
        clauses.append(exists(select(1).where(
            document_teams.c.document_id == Document.id,
            document_teams.c.team_id == parsed.team_id,
        )))
    if parsed.tag_id:
        clauses.append(exists(select(1).where(
            document_tags.c.document_id == Document.id,
            document_tags.c.tag_id == parsed.tag_id,
        )))
    if parsed.classification_id:
        clauses.append(Document.classification_id == parsed.classification_id)
    if parsed.start:
        clauses.append(Document.uploaded_at >= parsed.start.astimezone(timezone.utc))
    if parsed.end:
        clauses.append(Document.uploaded_at < parsed.end.astimezone(timezone.utc))
    return clauses


def search_documents(
    db: Session,
    user_id: int,
    parsed: ParsedSearch,
    page: int,
    page_size: int,
):
    base = [document_active_workspace_clause(user_id), *_filters(parsed)]
    offset = (page - 1) * page_size
    if parsed.mode == "metadata":
        rows = db.scalars(
            select(Document)
            .where(*base)
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
            .offset(offset)
            .limit(page_size)
        ).all()
        return [(document, None, None, None) for document in rows]

    settings = get_settings()
    candidate_limit = min(
        settings.semantic_search_max_top_k,
        max((offset + page_size) * 3, page_size),
    )
    passages = hybrid_search(
        db=db,
        user_id=user_id,
        query=parsed.topic or "",
        top_k=candidate_limit,
    )

    first_passage_by_document = {}
    ranked_document_ids = []
    for passage in passages:
        if passage.document_id in first_passage_by_document:
            continue
        ranked_document_ids.append(passage.document_id)
        first_passage_by_document[passage.document_id] = passage
    if not ranked_document_ids:
        return []

    documents = db.scalars(
        select(Document).where(
            *base,
            Document.id.in_(ranked_document_ids),
        )
    ).all()
    documents_by_id = {document.id: document for document in documents}
    retained_ids = [
        document_id
        for document_id in ranked_document_ids
        if document_id in documents_by_id
    ][offset:offset + page_size]
    return [
        (
            documents_by_id[document_id],
            first_passage_by_document[document_id].chunk_id,
            first_passage_by_document[document_id].page_number,
            (
                first_passage_by_document[document_id].chunk_text,
                first_passage_by_document[document_id].similarity_score,
            ),
        )
        for document_id in retained_ids
    ]

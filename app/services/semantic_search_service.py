"""Permission-filtered pgvector semantic retrieval."""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence
import unicodedata

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentPage, UserDocumentPreference, document_teams, user_teams
from app.services.embedding_service import embed_query


def document_accessible_clause(user_id: int):
    return exists(select(1).select_from(document_teams.join(user_teams, document_teams.c.team_id == user_teams.c.team_id)).where(document_teams.c.document_id == Document.id, user_teams.c.user_id == user_id))


def document_archived_clause(user_id: int):
    """Correlated per-user archive state; it never grants document access."""
    return exists(
        select(1)
        .select_from(UserDocumentPreference)
        .where(
            UserDocumentPreference.user_id == user_id,
            UserDocumentPreference.document_id == Document.id,
            UserDocumentPreference.is_archived.is_(True),
        )
    )


def document_active_workspace_clause(user_id: int):
    """Require team authorization and absence from this user's archive."""
    return and_(
        document_accessible_clause(user_id),
        ~document_archived_clause(user_id),
    )


def accessible_document(db: Session, document_id: int, user_id: int) -> Document | None:
    return db.scalar(select(Document).where(Document.id == document_id, document_accessible_clause(user_id)))


@dataclass(frozen=True)
class SearchResult:
    document_id: int
    filename: str
    page_number: int
    chunk_id: int
    chunk_text: str
    similarity_score: float


def similarity_meets_threshold(score: float, minimum: float) -> bool:
    """Inclusive cosine-similarity relevance boundary."""
    return score >= minimum


_LEXICAL_STOP_WORDS = {
    "about", "accessible", "are", "contain", "contains", "document",
    "documents", "find", "for", "from", "have", "in", "is", "listed",
    "mentioned", "my", "of", "pdf", "pdfs", "resume", "resumes", "show",
    "the", "this", "what", "which", "with",
}


def _lexical_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return {
        token
        for token in re.findall(r"[^\W_]+", normalized, re.UNICODE)
        if len(token) >= 3 and token not in _LEXICAL_STOP_WORDS
    }


def has_lexical_relevance(query: str, filename: str, chunk_text: str) -> bool:
    """Conservative secondary gate for unscoped English/entity-like search.

    Cosine similarity remains the primary multilingual signal. For queries
    containing Latin-script substantive tokens, require at least one literal
    token in the title or passage so unrelated high-scoring E5 neighbors are
    not returned merely because they are the best available candidates.
    Non-Latin queries retain cosine-only behavior.
    """
    query_tokens = _lexical_tokens(query)
    if not query_tokens:
        return True
    if not any("a" <= character <= "z" for character in "".join(query_tokens)):
        return True
    evidence_tokens = _lexical_tokens(f"{Path(filename).stem} {chunk_text}")
    return bool(query_tokens & evidence_tokens)


def semantic_search(
    db: Session,
    user_id: int,
    query: str,
    top_k: int | None = None,
    document_ids: Sequence[int] | None = None,
) -> list[SearchResult]:
    settings = get_settings()
    limit = top_k or settings.semantic_search_top_k
    limit = min(limit, settings.semantic_search_max_top_k)
    if document_ids is not None and not document_ids:
        return []
    vector = embed_query(query)
    distance = DocumentChunkEmbedding.embedding.cosine_distance(vector).label("distance")
    clauses = [
        DocumentChunkEmbedding.embedding_version == settings.embedding_version,
        document_active_workspace_clause(user_id),
        distance <= 1.0 - settings.semantic_search_min_similarity,
    ]
    if document_ids is not None:
        clauses.append(Document.id.in_(tuple(dict.fromkeys(document_ids))))
    rows = db.execute(select(DocumentChunkEmbedding, DocumentChunk, Document, DocumentPage, distance).join(DocumentChunk, DocumentChunkEmbedding.chunk_id == DocumentChunk.id).join(Document, DocumentChunk.document_id == Document.id).join(DocumentPage, DocumentChunk.page_id == DocumentPage.id).where(*clauses).order_by(distance).limit(limit)).all()
    results = []
    for _, chunk, document, page, item_distance in rows:
        similarity = float(1 - item_distance)
        if not similarity_meets_threshold(similarity, settings.semantic_search_min_similarity):
            continue
        if document_ids is None and not has_lexical_relevance(
            query,
            document.filename,
            chunk.text,
        ):
            continue
        results.append(SearchResult(document_id=document.id, filename=document.filename, page_number=page.page_number, chunk_id=chunk.id, chunk_text=chunk.text, similarity_score=similarity))
    return results

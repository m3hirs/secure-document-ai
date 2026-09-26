"""Permission-filtered pgvector semantic retrieval."""
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentPage, document_teams, user_teams
from app.services.embedding_service import embed_query


def document_accessible_clause(user_id: int):
    return exists(select(1).select_from(document_teams.join(user_teams, document_teams.c.team_id == user_teams.c.team_id)).where(document_teams.c.document_id == Document.id, user_teams.c.user_id == user_id))


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


def semantic_search(db: Session, user_id: int, query: str, top_k: int | None = None) -> list[SearchResult]:
    settings = get_settings()
    limit = top_k or settings.semantic_search_top_k
    limit = min(limit, settings.semantic_search_max_top_k)
    vector = embed_query(query)
    distance = DocumentChunkEmbedding.embedding.cosine_distance(vector).label("distance")
    rows = db.execute(select(DocumentChunkEmbedding, DocumentChunk, Document, DocumentPage, distance).join(DocumentChunk, DocumentChunkEmbedding.chunk_id == DocumentChunk.id).join(Document, DocumentChunk.document_id == Document.id).join(DocumentPage, DocumentChunk.page_id == DocumentPage.id).where(DocumentChunkEmbedding.embedding_version == settings.embedding_version, document_accessible_clause(user_id)).order_by(distance).limit(limit)).all()
    return [SearchResult(document_id=document.id, filename=document.filename, page_number=page.page_number, chunk_id=chunk.id, chunk_text=chunk.text, similarity_score=float(1 - item_distance)) for _, chunk, document, page, item_distance in rows]

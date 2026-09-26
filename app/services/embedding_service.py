"""Local E5 embedding generation and persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentEvent


@lru_cache
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model_name, cache_folder=str(settings.embedding_model_cache_dir), device="cpu", local_files_only=True)


def _encode(texts: list[str], prefix: str, model=None) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    active_model = model or get_embedding_model()
    vectors = active_model.encode([prefix + text for text in texts], batch_size=settings.embedding_batch_size, normalize_embeddings=True, show_progress_bar=False)
    result = [list(map(float, vector)) for vector in vectors]
    if any(len(vector) != settings.embedding_dimension for vector in result):
        raise ValueError("Embedding dimension mismatch")
    return result


def embed_passages(texts: list[str], model=None) -> list[list[float]]:
    return _encode(texts, "passage: ", model)


def embed_query(text: str, model=None) -> list[float]:
    if not text.strip():
        raise ValueError("Query must not be empty")
    return _encode([text], "query: ", model)[0]


def embed_document(db: Session, document: Document, encoder: Callable[[list[str]], list[list[float]]] = embed_passages) -> Document:
    settings = get_settings()
    document.embedding_status = "embedding"
    document.embedding_error = None
    db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="embedding_started", event_metadata={"embedding_version": settings.embedding_version}))
    db.commit()
    try:
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.id)).all()
        existing = {row.chunk_id: row for row in db.scalars(select(DocumentChunkEmbedding).join(DocumentChunk).where(DocumentChunk.document_id == document.id, DocumentChunkEmbedding.embedding_version == settings.embedding_version)).all()}
        count = 0
        for offset in range(0, len(chunks), settings.embedding_batch_size):
            batch = chunks[offset:offset + settings.embedding_batch_size]
            for chunk, vector in zip(batch, encoder([item.text for item in batch]), strict=True):
                row = existing.get(chunk.id)
                if row is None:
                    db.add(DocumentChunkEmbedding(chunk_id=chunk.id, embedding=vector, embedding_model=settings.embedding_model_name, embedding_version=settings.embedding_version))
                else:
                    row.embedding = vector
                    row.embedding_model = settings.embedding_model_name
                count += 1
        document.embedding_status = "embedded"
        document.embedding_count = count
        document.embedded_at = datetime.now(timezone.utc)
        document.embedding_version = settings.embedding_version
        db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="embedding_completed", event_metadata={"embedding_count": count, "embedding_version": settings.embedding_version}))
    except Exception:
        document.embedding_status = "failed"
        document.embedding_error = "Embedding generation failed"
        db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="embedding_failed", event_metadata={"embedding_version": settings.embedding_version}))
    db.commit()
    db.refresh(document)
    return document

"""Deterministic, page-aware normalization and text chunking."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, DocumentEvent, DocumentPage


@dataclass(frozen=True)
class ChunkPiece:
    text: str
    start: int
    end: int


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def _preferred_end(text: str, start: int, maximum: int) -> int:
    limit = min(start + maximum, len(text))
    if limit == len(text):
        return limit
    window = text[start:limit]
    candidates = [window.rfind("\n\n"), max(window.rfind(mark) for mark in (". ", "! ", "? "))]
    boundary = max(candidates)
    if boundary > maximum // 3:
        return start + boundary + (2 if window[boundary:boundary + 2] == "\n\n" else 1)
    whitespace = window.rfind(" ")
    return start + whitespace if whitespace > 0 else limit


def chunk_text(value: str | None, maximum: int | None = None, overlap: int | None = None) -> list[ChunkPiece]:
    settings = get_settings()
    maximum = maximum if maximum is not None else settings.chunk_max_characters
    overlap = overlap if overlap is not None else settings.chunk_overlap_characters
    text = normalize_text(value)
    if not text:
        return []
    pieces: list[ChunkPiece] = []
    start = 0
    while start < len(text):
        end = _preferred_end(text, start, maximum)
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start >= end:
            break
        pieces.append(ChunkPiece(text[start:end], start, end))
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = next_start
    return pieces


def approximate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def rechunk_document(db: Session, document: Document) -> Document:
    """Replace chunks for one document only, preserving all other documents."""
    settings = get_settings()
    document.chunking_status = "chunking"
    document.chunking_error = None
    db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="chunking_started", event_metadata=None))
    db.commit()
    try:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        count = 0
        pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_number)).all()
        for page in pages:
            for index, piece in enumerate(chunk_text(page.extracted_text)):
                db.add(DocumentChunk(document_id=document.id, page_id=page.id, chunk_index=index, text=piece.text, character_count=len(piece.text), token_count=approximate_token_count(piece.text), source_start_char=piece.start, source_end_char=piece.end, chunk_metadata={"chunking_version": settings.chunking_version, "ocr_source": page.ocr_used}))
                count += 1
        document.chunk_count = count
        document.chunking_status = "chunked"
        document.chunked_at = datetime.now(timezone.utc)
        document.chunking_version = settings.chunking_version
        db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="chunking_completed", event_metadata={"chunk_count": count, "chunking_version": settings.chunking_version}))
    except Exception:
        document.chunking_status = "failed"
        document.chunking_error = "Document chunking failed"
        db.add(DocumentEvent(document=document, user_id=document.uploaded_by, event_type="chunking_failed", event_metadata=None))
    db.commit()
    db.refresh(document)
    if document.chunking_status == "chunked":
        from app.services.embedding_service import embed_document
        return embed_document(db, document)
    return document

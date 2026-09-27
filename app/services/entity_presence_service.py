"""Deterministic, SQL-authorized lexical checks for entity-presence questions."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentPage
from app.schemas.rag import RagSourceRead
from app.services.semantic_search_service import document_active_workspace_clause


_PRESENCE_PATTERNS = (
    re.compile(
        r"^\s*is\s+there\s+any\s+(?:accessible\s+)?(?:documents?|pdfs?|resumes?)\s+"
        r"(?:containing|that\s+contains?|named|with(?:\s+(?:the\s+name|named))?)\s+"
        r"(?P<entity>.+?)\s*(?:in\s+it)?\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*do\s+we\s+have\s+(?:an?\s+)?(?:documents?|pdfs?|resumes?)\s+"
        r"(?:for|containing|named)\s+(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*is\s+(?P<entity>.+?)\s+mentioned\s+in\s+any\s+"
        r"(?:accessible\s+)?(?:documents?|pdfs?|resumes?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*does\s+any\s+(?:accessible\s+)?(?:documents?|pdfs?|resumes?)\s+"
        r"contain\s+(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*find\s+(?:an?\s+)?(?:accessible\s+)?(?:documents?|pdfs?|resumes?)\s+"
        r"containing\s+(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
)

_COUNT_PATTERNS = (
    re.compile(
        r"^\s*how\s+many\s+(?P<kind>documents?|pdfs?|resumes?)\s+"
        r"(?:contain(?:s|ing)?|have|has|with)\s+(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:the\s+)?(?:number|count)\s+of\s+"
        r"(?P<kind>documents?|pdfs?|resumes?)\s+"
        r"(?:that\s+)?(?:contain(?:s|ing)?|have|has|with)\s+"
        r"(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*count\s+(?:the\s+)?(?P<kind>documents?|pdfs?|resumes?)\s+"
        r"(?:that\s+)?(?:contain(?:s|ing)?|have|has|with)\s+"
        r"(?P<entity>.+?)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
)

_NAMED_TARGET_PATTERNS = (
    re.compile(
        r"^\s*summarize\s+(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*give\s+me\s+(?:a\s+)?summary\s+of\s+(?P<entity>.+?)\s+"
        r"(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+(?:technologies|skills|projects|experience)\s+(?:are\s+)?(?:listed\s+)?"
        r"(?:in|of)\s+(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+(?:technologies|skills|projects|experience)\s+(?:are\s+)?(?:listed\s+)?"
        r"(?:in|of)\s+(?P<entity>.+?)(?:['’]s)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*tell\s+me\s+about\s+(?P<entity>.+?)\s+"
        r"(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:skills|projects|experience)\s+(?:in|of)\s+"
        r"(?P<entity>.+?)(?:\s+(?:resume|pdf|document))?\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!,:;]*\s*$",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class EntityPresenceIntent:
    entity: str


@dataclass(frozen=True)
class EntityCountIntent:
    entity: str
    document_kind: str


@dataclass(frozen=True)
class NamedTargetIntent:
    entity: str


@dataclass(frozen=True)
class EntityPresenceResult:
    sources: list[RagSourceRead]
    exhaustive: bool
    entity_found: bool


@dataclass(frozen=True)
class EntityCountResult:
    sources: list[RagSourceRead]
    exhaustive: bool
    matching_document_count: int
    verified_document_count: int


@dataclass(frozen=True)
class NamedTargetResolution:
    document_ids: tuple[int, ...]
    exhaustive: bool


def normalize_literal(value: str) -> str:
    """Normalize Unicode, case, and whitespace without fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def normalized_literal_occurs(entity: str, evidence: str) -> bool:
    """Require a normalized literal without matching inside a larger word."""
    normalized_entity = normalize_literal(entity)
    normalized_evidence = normalize_literal(evidence)
    if not normalized_entity or not normalized_evidence:
        return False
    return re.search(
        rf"(?<!\w){re.escape(normalized_entity)}(?!\w)",
        normalized_evidence,
    ) is not None


def matching_literal_text(entity: str, evidence: str) -> str | None:
    """Return evidence casing for a literal match without returning context."""
    normalized_entity = unicodedata.normalize("NFKC", entity).strip()
    normalized_evidence = unicodedata.normalize("NFKC", evidence)
    tokens = re.split(r"\s+", normalized_entity)
    if not tokens or any(not token for token in tokens):
        return None
    whitespace = r"\s+"
    match = re.search(
        rf"(?<!\w){whitespace.join(re.escape(token) for token in tokens)}(?!\w)",
        normalized_evidence,
        re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else None


def detect_entity_presence_question(question: str) -> EntityPresenceIntent | None:
    """Recognize only explicit document entity-presence question shapes."""
    for pattern in _PRESENCE_PATTERNS:
        match = pattern.fullmatch(question)
        if match is None:
            continue
        entity = match.group("entity").strip().strip("\"'“”‘’ ")
        entity = re.sub(r"\s+", " ", entity)
        if (
            1 <= len(entity.split()) <= 8
            and 2 <= len(entity) <= 120
            and any(character.isalnum() for character in entity)
            and not any(unicodedata.category(character).startswith("C") for character in entity)
        ):
            return EntityPresenceIntent(entity=entity)
    return None


def _clean_entity(value: str) -> str:
    # Count-query punctuation belongs to the request, never to the literal
    # entity. Strip it before suffix cleanup so conversational forms ending
    # in "name in it?" can also remove that suffix.
    entity = re.sub(r"[?!.,:;]+\s*$", "", value.strip()).strip("\"'“”‘’ ")
    entity = re.sub(r"^\s*(?:the\s+)?(?:exact\s+)?name\s+", "", entity, flags=re.IGNORECASE)
    entity = re.sub(r"\s+name\s+in\s+(?:it|them)\s*$", "", entity, flags=re.IGNORECASE)
    entity = re.sub(r"\s+in\s+(?:it|them)\s*$", "", entity, flags=re.IGNORECASE)
    entity = re.sub(r"\s+name\s*$", "", entity, flags=re.IGNORECASE)
    entity = re.sub(r"[?!.,:;]+\s*$", "", entity)
    return re.sub(r"\s+", " ", entity).strip()


def _valid_entity(entity: str) -> bool:
    return (
        1 <= len(entity.split()) <= 8
        and 2 <= len(entity) <= 120
        and any(character.isalnum() for character in entity)
        and not any(unicodedata.category(character).startswith("C") for character in entity)
    )


def detect_entity_count_question(question: str) -> EntityCountIntent | None:
    """Recognize explicit requests to count documents containing a literal."""
    for pattern in _COUNT_PATTERNS:
        match = pattern.fullmatch(question)
        if match is None:
            continue
        entity = _clean_entity(match.group("entity"))
        if not _valid_entity(entity):
            continue
        kind = match.group("kind").casefold()
        if kind.startswith("pdf"):
            document_kind = "PDF"
        elif kind.startswith("resume"):
            document_kind = "resume"
        else:
            document_kind = "document"
        return EntityCountIntent(entity=entity, document_kind=document_kind)
    return None


def detect_named_target_question(question: str) -> NamedTargetIntent | None:
    """Conservatively extract a literal target from content questions."""
    excluded = {"my", "the", "this", "that", "a", "an", "accessible", "current"}
    for pattern in _NAMED_TARGET_PATTERNS:
        match = pattern.fullmatch(question)
        if match is None:
            continue
        entity = _clean_entity(match.group("entity"))
        entity = re.sub(r"(?:['’]s)\s*$", "", entity, flags=re.IGNORECASE).strip()
        words = entity.split()
        if (
            not _valid_entity(entity)
            or not 2 <= len(words) <= 8
            or normalize_literal(entity) in excluded
            or any(normalize_literal(word) in excluded for word in words)
        ):
            continue
        return NamedTargetIntent(entity=entity)
    return None


def resolve_authorized_named_target(
    db: Session,
    user_id: int,
    entity: str,
) -> NamedTargetResolution:
    """Resolve a literal only inside the active SQL-authorized page corpus."""
    if not normalize_literal(entity):
        return NamedTargetResolution(document_ids=(), exhaustive=False)

    document_rows = db.execute(
        select(Document.id, Document.page_count, Document.processing_status)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id)
    ).all()
    if not document_rows:
        return NamedTargetResolution(document_ids=(), exhaustive=True)

    page_rows = db.execute(
        select(DocumentPage, Document)
        .join(Document, DocumentPage.document_id == Document.id)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id, DocumentPage.page_number)
    ).all()
    page_counts = Counter(page.document_id for page, _document in page_rows)
    exhaustive = all(
        document.processing_status == "processed"
        and document.page_count is not None
        and page_counts[document.id] == document.page_count
        for document in document_rows
    ) and all(page.has_text for page, _document in page_rows)
    document_ids = tuple(sorted({
        page.document_id
        for page, _document in page_rows
        if normalized_literal_occurs(entity, page.extracted_text or "")
    }))
    return NamedTargetResolution(document_ids=document_ids, exhaustive=exhaustive)


def search_authorized_entity_count(
    db: Session,
    user_id: int,
    entity: str,
    source_limit: int,
) -> EntityCountResult:
    """Count distinct active, SQL-authorized documents containing a literal.

    Document and page rows are authorization-filtered in SQL. The count is
    derived from the complete normalized page corpus, never semantic similarity
    or model output. At most one literal-matching chunk source is returned per
    matching document so repeated chunks cannot inflate either count or sources.
    """
    if not normalize_literal(entity):
        return EntityCountResult(sources=[], exhaustive=False, matching_document_count=0, verified_document_count=0)

    document_rows = db.execute(
        select(Document.id, Document.page_count, Document.processing_status)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id)
    ).all()
    if not document_rows:
        return EntityCountResult(sources=[], exhaustive=True, matching_document_count=0, verified_document_count=0)

    page_rows = db.execute(
        select(DocumentPage, Document)
        .join(Document, DocumentPage.document_id == Document.id)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id, DocumentPage.page_number)
    ).all()
    page_counts = Counter(page.document_id for page, _document in page_rows)
    exhaustive = all(
        document.processing_status == "processed"
        and document.page_count is not None
        and page_counts[document.id] == document.page_count
        for document in document_rows
    ) and all(page.has_text for page, _document in page_rows)

    complete_document_ids = {
        document.id
        for document in document_rows
        if document.processing_status == "processed"
        and document.page_count is not None
        and page_counts[document.id] == document.page_count
        and all(page.has_text for page, _candidate in page_rows if page.document_id == document.id)
    }

    matching_page_ids = {
        page.id
        for page, _document in page_rows
        if page.document_id in complete_document_ids
        and normalized_literal_occurs(entity, page.extracted_text or "")
    }
    matching_document_ids = {
        page.document_id
        for page, _document in page_rows
        if page.id in matching_page_ids
    }
    if not matching_document_ids:
        return EntityCountResult(
            sources=[],
            exhaustive=exhaustive,
            matching_document_count=0,
            verified_document_count=0,
        )

    chunk_rows = db.execute(
        select(DocumentChunk, DocumentPage, Document)
        .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            document_active_workspace_clause(user_id),
            Document.id.in_(matching_document_ids),
            DocumentPage.id.in_(matching_page_ids),
        )
        .order_by(Document.id, DocumentPage.page_number, DocumentChunk.chunk_index)
    ).all()

    sources: list[RagSourceRead] = []
    sourced_documents: set[int] = set()
    verified_document_ids: set[int] = set()
    for chunk, page, document in chunk_rows:
        if not normalized_literal_occurs(entity, chunk.text):
            continue
        verified_document_ids.add(document.id)
        if document.id not in sourced_documents and len(sources) < source_limit:
            sources.append(
                RagSourceRead(
                    source_id=f"S{len(sources) + 1}",
                    document_id=document.id,
                    filename=document.filename,
                    page_number=page.page_number,
                    chunk_id=chunk.id,
                    snippet=chunk.text,
                    similarity=1.0,
                )
            )
            sourced_documents.add(document.id)

    return EntityCountResult(
        sources=sources,
        exhaustive=exhaustive,
        matching_document_count=len(matching_document_ids),
        verified_document_count=len(verified_document_ids),
    )


def search_authorized_entity_presence(
    db: Session,
    user_id: int,
    entity: str,
    source_limit: int,
) -> EntityPresenceResult:
    """Search the complete extracted text of SQL-authorized documents.

    All three queries include the shared authorization predicate before text is
    returned. Page text establishes whether the authorized extracted corpus was
    exhaustively checked. Positive source cards are emitted only for authorized
    chunks that themselves contain the normalized literal.
    """
    normalized_entity = normalize_literal(entity)
    if not normalized_entity:
        return EntityPresenceResult(sources=[], exhaustive=False, entity_found=False)

    document_rows = db.execute(
        select(
            Document.id,
            Document.page_count,
            Document.processing_status,
        )
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id)
    ).all()
    document_ids = [row.id for row in document_rows]
    if not document_ids:
        return EntityPresenceResult(sources=[], exhaustive=True, entity_found=False)

    page_rows = db.execute(
        select(DocumentPage, Document)
        .join(Document, DocumentPage.document_id == Document.id)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id, DocumentPage.page_number)
    ).all()
    page_counts = Counter(page.document_id for page, _document in page_rows)
    exhaustive = all(
        document.processing_status == "processed"
        and document.page_count is not None
        and page_counts[document.id] == document.page_count
        for document in document_rows
    ) and all(page.has_text for page, _document in page_rows)

    matching_page_ids = {
        page.id
        for page, _document in page_rows
        if normalized_literal_occurs(entity, page.extracted_text or "")
    }
    if not matching_page_ids:
        return EntityPresenceResult(
            sources=[],
            exhaustive=exhaustive,
            entity_found=False,
        )

    chunk_rows = db.execute(
        select(DocumentChunk, DocumentPage, Document)
        .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            document_active_workspace_clause(user_id),
            DocumentPage.id.in_(matching_page_ids),
        )
        .order_by(Document.id, DocumentPage.page_number, DocumentChunk.chunk_index)
    ).all()

    sources: list[RagSourceRead] = []
    for chunk, page, document in chunk_rows:
        if not normalized_literal_occurs(entity, chunk.text):
            continue
        sources.append(
            RagSourceRead(
                source_id=f"S{len(sources) + 1}",
                document_id=document.id,
                filename=document.filename,
                page_number=page.page_number,
                chunk_id=chunk.id,
                snippet=chunk.text,
                similarity=1.0,
            )
        )
        if len(sources) >= source_limit:
            break

    # A page-level match without a supporting chunk cannot produce a verified
    # public source. Fail closed rather than fabricating chunk metadata.
    return EntityPresenceResult(
        sources=sources,
        exhaustive=exhaustive,
        entity_found=True,
    )

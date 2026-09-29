"""Deterministic, SQL-authorized lexical checks for entity-presence questions."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentPage
from app.schemas.rag import RagSourceRead
from app.services.query_normalization import (
    document_name_aliases,
    normalize_document_name,
    normalize_literal_text,
)
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

_NAMED_TARGET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^\s*(?:give\s+me\s+)?(?:a\s+)?summary\s+of\s+"
            r"(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "summary",
    ),
    (
        re.compile(
            r"^\s*summari[sz]e\s+(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "summary",
    ),
    (
        re.compile(
            r"^\s*tell\s+me\s+about\s+(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "overview",
    ),
    (
        re.compile(
            r"^\s*what\s+is\s+in\s+(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "contents",
    ),
    (
        re.compile(
            r"^\s*explain\s+(?:the\s+)?document\s+(?:called|named)\s+"
            r"(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "explanation",
    ),
    (
        re.compile(
            r"^\s*information\s+from\s+(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "information",
    ),
    (
        re.compile(
            r"^\s*(?P<entity>.+?\s+resum)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "contents",
    ),
    (
        re.compile(
            r"^\s*(?:what\s+)?(?P<topic>technologies|skills|projects|experience|"
            r"programming\s+languages|(?:machine\s+learning|ml)\s+"
            r"(?:frameworks|libraries))\s+(?:are\s+)?(?:listed\s+)?"
            r"(?:in|of)\s+(?P<entity>.+?)\s*[?.!]*\s*$",
            re.IGNORECASE,
        ),
        "topic",
    ),
    # Retained conservative legacy shapes.
    (
    re.compile(
        r"^\s*summarize\s+(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "summary",
    ),
    (
    re.compile(
        r"^\s*give\s+me\s+(?:a\s+)?summary\s+of\s+(?P<entity>.+?)\s+"
        r"(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "summary",
    ),
    (
    re.compile(
        r"^\s*what\s+(?:technologies|skills|projects|experience)\s+(?:are\s+)?(?:listed\s+)?"
        r"(?:in|of)\s+(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "topic",
    ),
    (
    re.compile(
        r"^\s*what\s+(?:technologies|skills|projects|experience)\s+(?:are\s+)?(?:listed\s+)?"
        r"(?:in|of)\s+(?P<entity>.+?)(?:['’]s)\s+(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "topic",
    ),
    (
    re.compile(
        r"^\s*tell\s+me\s+about\s+(?P<entity>.+?)\s+"
        r"(?:resume|pdf|document)\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "overview",
    ),
    (
    re.compile(
        r"^\s*(?:skills|projects|experience)\s+(?:in|of)\s+"
        r"(?P<entity>.+?)(?:\s+(?:resume|pdf|document))?\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
        "topic",
    ),
    (
    re.compile(
        r"^\s*(?P<entity>.+?)\s+(?:resume|pdf|document)\s*[?.!,:;]*\s*$",
        re.IGNORECASE,
    ),
        "contents",
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
    topic: str | None = None


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
    ambiguous: bool = False
    match_type: str | None = None


def normalize_literal(value: str) -> str:
    """Normalize Unicode, case, and whitespace without fuzzy matching."""
    return normalize_literal_text(value)


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
    for pattern, default_topic in _NAMED_TARGET_PATTERNS:
        match = pattern.fullmatch(question)
        if match is None:
            continue
        entity = _clean_entity(match.group("entity"))
        entity = re.sub(r"\.pdf\s*$", "", entity, flags=re.IGNORECASE)
        entity = re.sub(
            r"(?:['’]s)?\s+(?:documents?|pdfs?|resumes?)\s*$",
            "",
            entity,
            flags=re.IGNORECASE,
        ).strip()
        entity = re.sub(r"(?:['’]s)\s*$", "", entity, flags=re.IGNORECASE).strip()
        words = entity.split()
        normalized_entity = normalize_document_name(entity)
        has_document_signal = bool(
            re.search(
                r"(?:\.pdf\b|\b(?:documents?|pdfs?|resum(?:e)?s?)\b)",
                question,
                re.IGNORECASE,
            )
        )
        explicit_document_reference = bool(
            re.search(r"\b(?:called|named|information\s+from)\b", question, re.IGNORECASE)
        )
        topic_reference = default_topic == "topic" and len(words) >= 2
        invalid_target = (
            not _valid_entity(entity)
            or not 1 <= len(words) <= 12
            or normalize_literal(entity) in excluded
            or all(normalize_literal(word) in excluded for word in words)
            or not normalized_entity
            or not (has_document_signal or explicit_document_reference or topic_reference)
        )
        if invalid_target:
            # Once an explicit action shape matched, do not let a looser suffix
            # pattern reinterpret the whole question as a filename.
            return None
        topic = match.groupdict().get("topic") or default_topic
        return NamedTargetIntent(entity=entity, topic=topic)
    return None


def resolve_authorized_named_target(
    db: Session,
    user_id: int,
    entity: str,
) -> NamedTargetResolution:
    """Resolve a target only inside the active SQL-authorized workspace.

    Filename evidence takes precedence over page-content aliases. Conservative
    fuzzy matching is attempted only after exact filename and content matches.
    Ambiguous candidates are never silently selected.
    """
    if not normalize_literal(entity):
        return NamedTargetResolution(document_ids=(), exhaustive=False)

    documents = db.scalars(
        select(Document)
        .where(document_active_workspace_clause(user_id))
        .order_by(Document.id)
    ).all()
    if not documents:
        return NamedTargetResolution(document_ids=(), exhaustive=True)

    raw_target = unicodedata.normalize("NFKC", entity).strip().casefold()
    normalized_target = normalize_document_name(entity, strip_extension=False)
    target_aliases = set(document_name_aliases(entity))

    exact_filename = [
        document.id
        for document in documents
        if unicodedata.normalize("NFKC", document.filename).strip().casefold() == raw_target
    ]
    if exact_filename:
        return NamedTargetResolution(
            document_ids=tuple(exact_filename) if len(exact_filename) == 1 else (),
            exhaustive=True,
            ambiguous=len(exact_filename) > 1,
            match_type="exact_filename",
        )

    normalized_filename = [
        document.id
        for document in documents
        if normalize_document_name(document.filename, strip_extension=False) == normalized_target
    ]
    if normalized_filename:
        return NamedTargetResolution(
            document_ids=tuple(normalized_filename) if len(normalized_filename) == 1 else (),
            exhaustive=True,
            ambiguous=len(normalized_filename) > 1,
            match_type="normalized_filename",
        )

    basename_matches = [
        document.id
        for document in documents
        if target_aliases.intersection(document_name_aliases(document.filename))
    ]
    if basename_matches:
        return NamedTargetResolution(
            document_ids=tuple(basename_matches) if len(basename_matches) == 1 else (),
            exhaustive=True,
            ambiguous=len(basename_matches) > 1,
            match_type="normalized_basename",
        )

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
        for document in documents
    ) and all(page.has_text for page, _document in page_rows)

    content_aliases = [
        alias
        for alias in target_aliases
        if alias and alias not in {"document", "pdf", "resume"}
    ]
    content_ids = tuple(sorted({
        page.document_id
        for page, _document in page_rows
        if any(
            normalized_literal_occurs(alias, page.extracted_text or "")
            for alias in content_aliases
        )
    }))
    if content_ids:
        return NamedTargetResolution(
            document_ids=content_ids if len(content_ids) == 1 else (),
            exhaustive=exhaustive,
            ambiguous=len(content_ids) > 1,
            match_type="content_alias",
        )

    target_key = next(iter(document_name_aliases(entity)), "")
    fuzzy_scores: list[tuple[float, int]] = []
    target_tokens = set(target_key.split())
    for document in documents:
        best = 0.0
        for alias in document_name_aliases(document.filename):
            if not target_tokens.intersection(alias.split()):
                continue
            best = max(best, SequenceMatcher(None, target_key, alias).ratio())
        if best >= 0.86:
            fuzzy_scores.append((best, document.id))

    if not fuzzy_scores:
        return NamedTargetResolution(document_ids=(), exhaustive=exhaustive)
    fuzzy_scores.sort(key=lambda item: (-item[0], item[1]))
    best_score = fuzzy_scores[0][0]
    plausible = [
        document_id
        for score, document_id in fuzzy_scores
        if best_score - score <= 0.03
    ]
    return NamedTargetResolution(
        document_ids=(plausible[0],) if len(plausible) == 1 else (),
        exhaustive=exhaustive,
        ambiguous=len(plausible) > 1,
        match_type="fuzzy_filename",
    )


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

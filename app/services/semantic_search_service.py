"""Permission-filtered pgvector semantic retrieval."""
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentPage, UserDocumentPreference, document_teams, user_teams
from app.services.embedding_service import embed_query
from app.services.query_normalization import (
    lexical_query_tokens,
    normalize_search_text,
    normalized_filename_stem,
)


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


def has_lexical_relevance(query: str, filename: str, chunk_text: str) -> bool:
    """Conservative secondary gate for unscoped English/entity-like search.

    Cosine similarity remains the primary multilingual signal. For queries
    containing Latin-script substantive tokens, require at least one literal
    token in the title or passage so unrelated high-scoring E5 neighbors are
    not returned merely because they are the best available candidates.
    Non-Latin queries retain cosine-only behavior.
    """
    query_tokens = set(lexical_query_tokens(query))
    if not query_tokens:
        return True
    if not any("a" <= character <= "z" for character in "".join(query_tokens)):
        return True
    evidence_tokens = set(lexical_query_tokens(f"{filename} {chunk_text}"))
    return bool(query_tokens & evidence_tokens)


def semantic_search(
    db: Session,
    user_id: int,
    query: str,
    top_k: int | None = None,
    document_ids: Sequence[int] | None = None,
    *,
    require_lexical_support: bool = True,
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
        if require_lexical_support and document_ids is None and not has_lexical_relevance(
            query,
            document.filename,
            chunk.text,
        ):
            continue
        results.append(SearchResult(document_id=document.id, filename=document.filename, page_number=page.page_number, chunk_id=chunk.id, chunk_text=chunk.text, similarity_score=similarity))
    return results


@dataclass(frozen=True)
class _LexicalHit:
    result: SearchResult
    strength: float
    exact_phrase: bool


def _lexical_strength(query: str, filename: str, chunk_text: str) -> tuple[float, bool]:
    terms = lexical_query_tokens(query)
    if not terms:
        return 0.0, False
    filename_text = normalized_filename_stem(filename)
    passage_text = normalize_search_text(chunk_text, singularize_document_words=True)
    normalized_query = normalize_search_text(
        query,
        strip_pdf_extension=True,
        singularize_document_words=True,
    )
    filename_hits = sum(term in filename_text.split() for term in terms)
    passage_tokens = set(passage_text.split())
    passage_hits = sum(term in passage_tokens for term in terms)
    exact_phrase = bool(
        normalized_query
        and (
            normalized_query in filename_text
            or normalized_query in passage_text
        )
    )
    strength = (
        (2.0 * filename_hits + passage_hits) / max(1, 3 * len(terms))
        + (1.0 if exact_phrase else 0.0)
    )
    return strength, exact_phrase


def lexical_search(
    db: Session,
    user_id: int,
    query: str,
    top_k: int,
    document_ids: Sequence[int] | None = None,
) -> list[_LexicalHit]:
    """Return SQL-authorized literal candidates ranked without embeddings."""
    terms = lexical_query_tokens(query)
    if not terms or (document_ids is not None and not document_ids):
        return []

    clauses = [document_active_workspace_clause(user_id)]
    if document_ids is not None:
        clauses.append(Document.id.in_(tuple(dict.fromkeys(document_ids))))
    lexical_predicates = [
        or_(
            func.lower(Document.filename).contains(term.casefold()),
            func.lower(DocumentChunk.text).contains(term.casefold()),
        )
        for term in terms
    ]
    rows = db.execute(
        select(DocumentChunk, Document, DocumentPage)
        .join(Document, DocumentChunk.document_id == Document.id)
        .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
        .where(*clauses, or_(*lexical_predicates))
        .order_by(Document.id, DocumentPage.page_number, DocumentChunk.chunk_index)
        .limit(min(max(top_k * 8, 40), 200))
    ).all()

    hits: list[_LexicalHit] = []
    for chunk, document, page in rows:
        strength, exact_phrase = _lexical_strength(
            query,
            document.filename,
            chunk.text,
        )
        if strength <= 0:
            continue
        hits.append(
            _LexicalHit(
                result=SearchResult(
                    document_id=document.id,
                    filename=document.filename,
                    page_number=page.page_number,
                    chunk_id=chunk.id,
                    chunk_text=chunk.text,
                    similarity_score=min(1.0, 0.75 + min(strength, 1.0) * 0.25),
                ),
                strength=strength,
                exact_phrase=exact_phrase,
            )
        )
    hits.sort(
        key=lambda hit: (
            not hit.exact_phrase,
            -hit.strength,
            hit.result.document_id,
            hit.result.page_number,
            hit.result.chunk_id,
        )
    )
    return hits[: min(max(top_k * 4, top_k), 100)]


def hybrid_search(
    db: Session,
    user_id: int,
    query: str,
    top_k: int | None = None,
    document_ids: Sequence[int] | None = None,
) -> list[SearchResult]:
    """Fuse independently authorized lexical and pgvector ranks with RRF."""
    settings = get_settings()
    limit = min(
        top_k or settings.semantic_search_top_k,
        settings.semantic_search_max_top_k,
    )
    if document_ids is not None and not document_ids:
        return []

    candidate_limit = min(
        max(limit * 4, 20),
        settings.semantic_search_max_top_k,
    )
    lexical_hits = lexical_search(
        db,
        user_id,
        query,
        candidate_limit,
        document_ids=document_ids,
    )
    semantic_hits = semantic_search(
        db,
        user_id,
        query,
        candidate_limit,
        document_ids=document_ids,
        require_lexical_support=False,
    )

    # Unscoped Latin-script semantic-only matches need a stronger score than
    # the normal hybrid threshold. This preserves multilingual semantic-only
    # retrieval while suppressing arbitrary nearest neighbors for nonsense.
    if not lexical_hits and document_ids is None:
        query_terms = lexical_query_tokens(query)
        contains_latin = any(
            "a" <= character <= "z"
            for character in "".join(query_terms).casefold()
        )
        if contains_latin:
            semantic_only_minimum = max(
                settings.semantic_search_min_similarity + 0.04,
                0.86,
            )
            semantic_hits = [
                hit
                for hit in semantic_hits
                if hit.similarity_score >= semantic_only_minimum
            ]

    rrf_constant = 60.0
    scores: dict[int, float] = {}
    results_by_chunk: dict[int, SearchResult] = {}
    lexical_exact: set[int] = set()
    semantic_scores: dict[int, float] = {}

    for rank, hit in enumerate(lexical_hits, start=1):
        chunk_id = hit.result.chunk_id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 2.0 / (rrf_constant + rank)
        results_by_chunk[chunk_id] = hit.result
        if hit.exact_phrase:
            lexical_exact.add(chunk_id)

    for rank, result in enumerate(semantic_hits, start=1):
        chunk_id = result.chunk_id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_constant + rank)
        results_by_chunk.setdefault(chunk_id, result)
        semantic_scores[chunk_id] = result.similarity_score

    ordered_chunk_ids = sorted(
        scores,
        key=lambda chunk_id: (
            chunk_id not in lexical_exact,
            -scores[chunk_id],
            -semantic_scores.get(
                chunk_id,
                results_by_chunk[chunk_id].similarity_score,
            ),
            results_by_chunk[chunk_id].document_id,
            results_by_chunk[chunk_id].page_number,
            chunk_id,
        ),
    )
    return [results_by_chunk[chunk_id] for chunk_id in ordered_chunk_ids[:limit]]

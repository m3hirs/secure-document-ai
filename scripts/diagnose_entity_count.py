"""Read-only, privacy-safe diagnostics for deterministic entity counting."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import SessionLocal
from app.db.models import Document, DocumentChunk, DocumentPage, UserDocumentPreference
from app.services.entity_presence_service import (
    normalize_literal,
    normalized_literal_occurs,
    search_authorized_entity_count,
)
from app.services.semantic_search_service import document_accessible_clause


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose entity-count fail-closed state without printing document content."
    )
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--entity", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entity = args.entity.strip()
    if args.user_id < 1 or not normalize_literal(entity):
        print("entity_count routing: FAIL")
        print("matching distinct documents: 0")
        print("verified source documents: 0")
        print("corpus exhaustive: NO")
        print("fail_closed_reason: invalid diagnostic arguments")
        return 2

    with SessionLocal() as db:
        documents = list(db.scalars(select(Document).order_by(Document.id)))
        page_rows = list(db.scalars(select(DocumentPage).order_by(DocumentPage.document_id, DocumentPage.page_number)))
        chunk_rows = list(db.scalars(select(DocumentChunk).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)))

        pages_by_document: dict[int, list[DocumentPage]] = {}
        chunks_by_document: dict[int, list[DocumentChunk]] = {}
        for page in page_rows:
            pages_by_document.setdefault(page.document_id, []).append(page)
        for chunk in chunk_rows:
            chunks_by_document.setdefault(chunk.document_id, []).append(chunk)

        authorized_ids = set(
            db.scalars(
                select(Document.id).where(document_accessible_clause(args.user_id))
            )
        )
        archived_ids = set(
            db.scalars(
                select(UserDocumentPreference.document_id).where(
                    UserDocumentPreference.user_id == args.user_id,
                    UserDocumentPreference.is_archived.is_(True),
                )
            )
        )
        active_authorized_ids = authorized_ids - archived_ids

        result = search_authorized_entity_count(
            db=db,
            user_id=args.user_id,
            entity=entity,
            source_limit=max(1, len(active_authorized_ids)),
        )
        verified_source_ids = {source.document_id for source in result.sources}

        incomplete_reasons: list[str] = []
        for document in documents:
            pages = pages_by_document.get(document.id, [])
            chunks = chunks_by_document.get(document.id, [])
            authorized = document.id in authorized_ids
            archived = document.id in archived_ids
            active_authorized = document.id in active_authorized_ids
            pages_complete = (
                document.processing_status == "processed"
                and document.page_count is not None
                and len(pages) == document.page_count
                and all(page.has_text for page in pages)
            )
            entity_match = any(
                normalized_literal_occurs(entity, page.extracted_text or "")
                for page in pages
            )
            verified_source = document.id in verified_source_ids

            print(f"document_id: {document.id}")
            print(f"filename: {document.filename}")
            print(f"authorized: {'YES' if authorized else 'NO'}")
            print(f"archived: {'YES' if archived else 'NO'}")
            print(f"declared_page_count: {document.page_count}")
            print(f"stored_page_count: {len(pages)}")
            print(f"chunk_count: {len(chunks)}")
            print(f"extracted_text_complete: {'YES' if pages_complete else 'NO'}")
            print(f"entity_match: {'YES' if entity_match else 'NO'}")
            print(f"verified_source_available: {'YES' if verified_source else 'NO'}")
            print("---")

            if not active_authorized or pages_complete:
                continue
            if document.processing_status != "processed":
                incomplete_reasons.append(
                    f"document {document.id} processing status is not processed"
                )
            elif document.page_count is None:
                incomplete_reasons.append(f"document {document.id} has no declared page count")
            elif len(pages) != document.page_count:
                incomplete_reasons.append(
                    f"document {document.id} page count does not match stored pages"
                )
            else:
                incomplete_reasons.append(
                    f"document {document.id} has a page with no extracted text"
                )

        if not result.exhaustive:
            reason = "; ".join(incomplete_reasons) or "authorized corpus completeness check failed"
            routing = "FAIL"
        elif result.matching_document_count > 0 and not result.sources:
            reason = "entity matched extracted pages but no matching verified chunk exists"
            routing = "FAIL"
        else:
            reason = "none"
            routing = "PASS"

        print(f"entity_count routing: {routing}")
        print(f"matching distinct documents: {result.matching_document_count}")
        print(f"verified source documents: {len(verified_source_ids)}")
        print(f"corpus exhaustive: {'YES' if result.exhaustive else 'NO'}")
        print(f"fail_closed_reason: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

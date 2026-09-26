"""Privacy-preserving, read-only Stage 8.2 RAG quality evaluation."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.services.llm_service import LocalLLMError
from app.services.rag_service import (
    answer_question,
    retrieve_authorized_passages,
    select_rag_context,
)


DIAGNOSTIC_USER_ID = 1
TOP_K = 10
RESTRICTED_DOCUMENT_ID = 35

QUESTIONS = (
    (
        "Q1",
        "What programming languages are listed in my resume?",
    ),
    (
        "Q2",
        "Which machine learning frameworks and libraries are mentioned in my resume?",
    ),
    (
        "Q3",
        "What technologies were used in the Responsible AI Risk Monitoring Platform?",
    ),
    (
        "Q4",
        "What technologies were used in the Yoga Posture Detection project?",
    ),
)


def _source_identity(source: object) -> tuple[object, object, object, object]:
    """Return non-content identifiers used to verify selected source membership."""
    return (
        source.source_id,
        source.document_id,
        source.page_number,
        source.chunk_id,
    )


def main() -> None:
    # Load the existing environment-backed configuration without printing it.
    get_settings()

    with SessionLocal() as db:
        for question_id, question in QUESTIONS:
            passages = retrieve_authorized_passages(
                db=db,
                user_id=DIAGNOSTIC_USER_ID,
                question=question,
                top_k=TOP_K,
            )

            retrieved_document_ids = [
                passage.document_id for passage in passages
            ]

            retrieved_chunk_identities = [
                (
                    passage.document_id,
                    passage.page_number,
                    passage.chunk_id,
                )
                for passage in passages
            ]

            selected_context = select_rag_context(passages, question)
            selected_sources = selected_context.sources

            selected_source_ids = [
                source.source_id for source in selected_sources
            ]

            selected_document_ids = [
                source.document_id for source in selected_sources
            ]

            selected_chunk_identities = [
                (
                    source.document_id,
                    source.page_number,
                    source.chunk_id,
                )
                for source in selected_sources
            ]

            print(f"Question ID: {question_id}")
            print(f"Retrieved passage count: {len(passages)}")
            print(f"Retrieved document IDs: {retrieved_document_ids}")

            print(
                "Retrieved chunk identities: "
                f"{retrieved_chunk_identities}"
            )

            print(f"Selected source IDs: {selected_source_ids}")

            print(
                "Selected chunk identities: "
                f"{selected_chunk_identities}"
            )

            print(
                "Selected context character count: "
                f"{len(selected_context.context)}"
            )

            if (
                RESTRICTED_DOCUMENT_ID in retrieved_document_ids
                or RESTRICTED_DOCUMENT_ID in selected_document_ids
            ):
                print("SECURITY FAILURE: restricted document retrieved")
                print("Evaluation aborted before Ollama: True")
                return

            try:
                result = answer_question(
                    db=db,
                    user_id=DIAGNOSTIC_USER_ID,
                    question=question,
                    top_k=TOP_K,
                )
            except LocalLLMError:
                print("Evaluation status: local Ollama unavailable")
                return

            returned_source_ids = [
                source.source_id for source in result.sources
            ]

            returned_document_ids = [
                source.document_id for source in result.sources
            ]

            selected_identities = {
                _source_identity(source) for source in selected_sources
            }

            every_returned_source_was_selected = all(
                _source_identity(source) in selected_identities
                for source in result.sources
            )

            print(
                "Final insufficient_evidence: "
                f"{result.insufficient_evidence}"
            )

            print(f"Final returned source IDs: {returned_source_ids}")

            print(f"Final returned document IDs: {returned_document_ids}")

            print(f"Answer character count: {len(result.answer)}")

            print(
                "Every returned source was selected and authorized: "
                f"{every_returned_source_was_selected}"
            )


if __name__ == "__main__":
    main()
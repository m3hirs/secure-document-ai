"""Read-only, metadata-only diagnostic for the local Stage 7 RAG path."""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.services.llm_service import LocalLLMError, generate_local_answer
from app.services.rag_service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    answer_question,
    retrieve_authorized_passages,
    select_rag_context,
)


DIAGNOSTIC_USER_ID = 1
QUESTION = "What programming languages and AI technologies are mentioned in my resume?"
TOP_K = 5
_CITATION_PATTERN = re.compile(r"\[(S\d+)\]")
_SOURCE_SPACE_PATTERN = re.compile(r"\bSource\s+(S\d+)\b", re.IGNORECASE)
_SOURCE_COLON_PATTERN = re.compile(r"\bSource\s*:\s*(S\d+)\b", re.IGNORECASE)
_PARENTHESIZED_SOURCE_PATTERN = re.compile(r"\((S\d+)\)")
_BARE_SOURCE_PATTERN = re.compile(r"(?<![\w\[\(:])(S\d+)\b(?![\w\]\)])")
_MARKDOWN_SOURCE_HEADING_PATTERN = re.compile(
    r"^\s{0,3}#{1,6}\s+(?:sources?|references?|citations?)\b",
    re.IGNORECASE | re.MULTILINE,
)
_MARKDOWN_SOURCE_LIST_PATTERN = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[?S\d+\]?|source\b)",
    re.IGNORECASE | re.MULTILINE,
)
_PROMPT_INSTRUCTION_MARKERS = (
    "trusted task instructions",
    "untrusted retrieved document passages",
    "source ids are supplied by the application",
    "every factual claim must have",
)


def _unique_ids(matches: list[str]) -> list[str]:
    return list(dict.fromkeys(matches))


def _bare_source_ids(answer: str) -> list[str]:
    """Find bare S# tokens while excluding the other reported formats."""
    source_ids: list[str] = []
    for match in _BARE_SOURCE_PATTERN.finditer(answer):
        prefix = answer[max(0, match.start() - 12):match.start()]
        if re.search(r"source\s*:?\s*$", prefix, re.IGNORECASE):
            continue
        source_ids.append(match.group(1))
    return _unique_ids(source_ids)


def _print_attempt_diagnostics(
    label: str,
    answer: str,
    selected_source_ids: list[str],
) -> bool:
    """Print metadata only and return whether citations are valid."""
    citation_ids = _unique_ids(_CITATION_PATTERN.findall(answer))
    selected_source_id_set = set(selected_source_ids)
    citations_valid = bool(citation_ids) and all(
        citation_id in selected_source_id_set
        for citation_id in citation_ids
    )

    print(f"{label} answer character count: {len(answer)}")
    print(
        f"{label} answer matches insufficient-evidence sentence: "
        f"{answer == INSUFFICIENT_EVIDENCE_ANSWER}"
    )
    print(f"{label} citation IDs: {citation_ids}")
    print(f"{label} citations valid against selected sources: {citations_valid}")

    alternative_formats = {
        "Source S#": _unique_ids(_SOURCE_SPACE_PATTERN.findall(answer)),
        "Source: S#": _unique_ids(_SOURCE_COLON_PATTERN.findall(answer)),
        "(S#)": _unique_ids(_PARENTHESIZED_SOURCE_PATTERN.findall(answer)),
        "bare S#": _bare_source_ids(answer),
    }
    for format_label, source_ids in alternative_formats.items():
        print(f"{label} alternative {format_label} present: {bool(source_ids)}")
        print(f"{label} alternative {format_label} IDs: {source_ids}")

    prompt_marker_count = sum(
        marker in answer.lower()
        for marker in _PROMPT_INSTRUCTION_MARKERS
    )
    print(
        f"{label} Markdown source heading present: "
        f"{bool(_MARKDOWN_SOURCE_HEADING_PATTERN.search(answer))}"
    )
    print(
        f"{label} Markdown source list present: "
        f"{bool(_MARKDOWN_SOURCE_LIST_PATTERN.search(answer))}"
    )
    print(f"{label} Markdown code fence present: {bool(re.search(r'```|~~~', answer))}")
    print(
        f"{label} repeated prompt instructions apparent: "
        f"{prompt_marker_count >= 2}"
    )
    print(f"{label} prompt instruction marker count: {prompt_marker_count}")
    return citations_valid


def main() -> None:
    # Loads the project's existing .env-backed settings without printing them.
    get_settings()

    with SessionLocal() as db:
        passages = retrieve_authorized_passages(
            db=db,
            user_id=DIAGNOSTIC_USER_ID,
            question=QUESTION,
            top_k=TOP_K,
        )
        retrieved_document_ids = [passage.document_id for passage in passages]
        retrieved_source_ids = [passage.source_id for passage in passages]

        print(f"Retrieved passage count: {len(passages)}")
        print(f"Retrieved document IDs: {retrieved_document_ids}")
        print(f"Retrieved source IDs: {retrieved_source_ids}")
        print(f"Document 31 retrieved: {31 in retrieved_document_ids}")
        print(f"Document 35 retrieved: {35 in retrieved_document_ids}")

        selected_context = select_rag_context(passages, QUESTION)
        selected_source_ids = [source.source_id for source in selected_context.sources]
        selected_document_ids = [source.document_id for source in selected_context.sources]

        print(f"Context empty: {not bool(selected_context.context)}")
        print(f"Context character count: {len(selected_context.context)}")
        print(f"Selected source IDs: {selected_source_ids}")

        if 35 in retrieved_document_ids or 35 in selected_document_ids:
            print("SECURITY FAILURE: restricted document retrieved")
            return

        if selected_context.context:
            try:
                first_answer = generate_local_answer(
                    QUESTION,
                    selected_context.context,
                )
            except LocalLLMError:
                print("Ollama status: unavailable")
                return

            first_citations_valid = _print_attempt_diagnostics(
                "First",
                first_answer,
                selected_source_ids,
            )

            # Match the orchestration rule: an exact insufficient-evidence
            # response is final and is not retried.
            if (
                first_answer != INSUFFICIENT_EVIDENCE_ANSWER
                and not first_citations_valid
            ):
                try:
                    retry_answer = generate_local_answer(
                        QUESTION,
                        selected_context.context,
                        citation_retry=True,
                    )
                except LocalLLMError:
                    print("Ollama status: unavailable")
                    return

                _print_attempt_diagnostics(
                    "Retry",
                    retry_answer,
                    selected_source_ids,
                )

        print(
            "Diagnostic note: calling answer_question may make additional local "
            "Ollama calls."
        )
        try:
            result = answer_question(
                db=db,
                user_id=DIAGNOSTIC_USER_ID,
                question=QUESTION,
                top_k=TOP_K,
            )
        except LocalLLMError:
            print("Ollama status: unavailable")
            return

        print(f"Final insufficient_evidence: {result.insufficient_evidence}")
        print(
            "Final returned source IDs: "
            f"{[source.source_id for source in result.sources]}"
        )
        print(
            "Final returned document IDs: "
            f"{[source.document_id for source in result.sources]}"
        )


if __name__ == "__main__":
    main()

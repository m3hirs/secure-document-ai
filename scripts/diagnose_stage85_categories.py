"""Privacy-safe, read-only diagnostics for Stage 8.5 category validation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.schemas.rag import RagSourceRead
from app.services.llm_service import (
    LocalLLMError,
    TECHNOLOGY_CATEGORIES,
    generate_local_categorized_answer,
)
from app.services.rag_service import (
    _API_ITEM_PATTERN,
    _API_ROLE_PATTERN,
    _INFRASTRUCTURE_ROLE_PATTERN,
    _explicit_category_sections,
    _normalize_evidence_text,
    _normalized_item_occurs,
    _source_explicitly_supports_item,
    classify_question_category,
    retrieve_authorized_passages,
    select_rag_context,
)


DIAGNOSTIC_USER_ID = 1
RESTRICTED_DOCUMENT_ID = 35
TOP_K = 5
QUESTIONS = (
    (
        "INFRA",
        "Which infrastructure or platform technologies are mentioned?",
    ),
    ("API", "Which API technologies are mentioned?"),
)
SAFE_CANDIDATE_LABELS = {
    "kafka": "Kafka",
    "kubernetes": "Kubernetes",
    "rest api": "REST API",
    "rest apis": "REST APIs",
    "api module": "API module",
    "api modules": "API modules",
    "fastapi": "FastAPI",
}


def _safe_candidate_label(value: object) -> str:
    if not isinstance(value, str):
        return "other"
    return SAFE_CANDIDATE_LABELS.get(_normalize_evidence_text(value), "other")


def _well_formed_source_ids(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(source_id, str) for source_id in value)
        and len(value) == len(set(value))
    )


def _authorized_cited_sources(
    source_ids: object,
    selected_source_map: dict[str, RagSourceRead],
) -> list[RagSourceRead]:
    if not _well_formed_source_ids(source_ids):
        return []
    return [
        selected_source_map[source_id]
        for source_id in source_ids
        if source_id in selected_source_map
    ]


def _recognized_section_kinds(
    sources: Sequence[RagSourceRead],
) -> list[str]:
    kinds = {
        section_kind
        for source in sources
        for section_kind, _ in _explicit_category_sections(source.snippet)
        if section_kind is not None
    }
    return sorted(kinds)


def _matching_category_section_found(
    sources: Sequence[RagSourceRead],
    item_text: object,
    requested_category: str | None,
) -> bool:
    if not isinstance(item_text, str) or requested_category is None:
        return False
    return any(
        section_kind == requested_category
        and _normalized_item_occurs(item_text, section_text)
        for source in sources
        for section_kind, section_text in _explicit_category_sections(source.snippet)
    )


def _infrastructure_same_sentence_role_found(
    sources: Sequence[RagSourceRead],
    item_text: object,
) -> bool:
    if not isinstance(item_text, str):
        return False
    return any(
        _normalized_item_occurs(item_text, sentence)
        and _INFRASTRUCTURE_ROLE_PATTERN.search(sentence) is not None
        for source in sources
        for sentence in re.split(r"[\r\n.!?]+", source.snippet)
    )


def _api_technical_section_rule_passed(
    sources: Sequence[RagSourceRead],
    item_text: object,
) -> bool:
    if not isinstance(item_text, str):
        return False

    normalized_item = _normalize_evidence_text(item_text)
    for source in sources:
        for section_kind, section_text in _explicit_category_sections(source.snippet):
            if section_kind != "technical_core" or not _normalized_item_occurs(
                item_text,
                section_text,
            ):
                continue

            if normalized_item != "fastapi":
                if _API_ITEM_PATTERN.search(normalized_item):
                    return True
                continue

            normalized_section = _normalize_evidence_text(section_text)
            item_position = normalized_section.find(normalized_item)
            if item_position < 0:
                continue
            evidence_window = normalized_section[
                max(0, item_position - 80):
                item_position + len(normalized_item) + 80
            ]
            if _API_ROLE_PATTERN.search(evidence_window):
                return True
    return False


def _print_item_diagnostics(
    index: int,
    raw_item: object,
    requested_category: str | None,
    selected_source_map: dict[str, RagSourceRead],
) -> None:
    item = raw_item if isinstance(raw_item, dict) else {}
    item_text = item.get("text")
    category = item.get("category")
    source_ids = item.get("source_ids")

    category_is_known = (
        isinstance(category, str) and category in TECHNOLOGY_CATEGORIES
    )
    category_matches = (
        category_is_known and category == requested_category
    )
    source_ids_well_formed = _well_formed_source_ids(source_ids)
    source_ids_authorized = (
        source_ids_well_formed
        and all(source_id in selected_source_map for source_id in source_ids)
    )
    cited_sources = _authorized_cited_sources(source_ids, selected_source_map)
    exact_occurrence = (
        isinstance(item_text, str)
        and bool(cited_sources)
        and any(
            _normalized_item_occurs(item_text, source.snippet)
            for source in cited_sources
        )
    )
    final_support = (
        isinstance(item_text, str)
        and bool(item_text.strip())
        and category_matches
        and source_ids_authorized
        and any(
            _source_explicitly_supports_item(
                source,
                item_text,
                requested_category,
            )
            for source in cited_sources
        )
    )

    print(f"Item index: {index}")
    print(f"Safe candidate label: {_safe_candidate_label(item_text)}")
    print(f"Category is known: {category_is_known}")
    print(f"Category matches requested category: {category_matches}")
    print(f"Source IDs well formed: {source_ids_well_formed}")
    print(f"Source IDs authorized: {source_ids_authorized}")
    print(f"Exact item text occurs in cited evidence: {exact_occurrence}")
    print(
        "Recognized section kinds present: "
        f"{_recognized_section_kinds(cited_sources)}"
    )
    print(
        "Matching category section found: "
        f"{_matching_category_section_found(cited_sources, item_text, requested_category)}"
    )
    print(
        "Infrastructure same-sentence role found: "
        f"{_infrastructure_same_sentence_role_found(cited_sources, item_text)}"
    )
    print(
        "API technical-section rule passed: "
        f"{_api_technical_section_rule_passed(cited_sources, item_text)}"
    )
    print(f"Final deterministic support result: {final_support}")


def _run_question(db: object, question_id: str, question: str) -> None:
    requested_category = classify_question_category(question)
    passages = retrieve_authorized_passages(
        db=db,
        user_id=DIAGNOSTIC_USER_ID,
        question=question,
        top_k=TOP_K,
    )
    retrieved_document_ids = [passage.document_id for passage in passages]
    selected_context = select_rag_context(passages, question)
    selected_source_ids = [
        source.source_id for source in selected_context.sources
    ]
    selected_document_ids = [
        source.document_id for source in selected_context.sources
    ]

    print(f"Question ID: {question_id}")
    print(f"Derived category: {requested_category}")
    print(f"Retrieved passage count: {len(passages)}")
    print(f"Retrieved document IDs: {retrieved_document_ids}")
    print(f"Selected source IDs: {selected_source_ids}")

    if (
        RESTRICTED_DOCUMENT_ID in retrieved_document_ids
        or RESTRICTED_DOCUMENT_ID in selected_document_ids
    ):
        print("SECURITY FAILURE: restricted document retrieved")
        raise SystemExit(1)

    if requested_category is None or not selected_context.context:
        print("Number of model answer_items: 0")
        return

    model_output = generate_local_categorized_answer(
        question,
        selected_context.context,
        requested_category,
        selected_source_ids,
    )
    answer_items = (
        model_output.get("answer_items")
        if isinstance(model_output, dict)
        else None
    )
    if not isinstance(answer_items, list):
        answer_items = []

    print(f"Number of model answer_items: {len(answer_items)}")
    selected_source_map = {
        source.source_id: source for source in selected_context.sources
    }
    for index, raw_item in enumerate(answer_items, start=1):
        _print_item_diagnostics(
            index,
            raw_item,
            requested_category,
            selected_source_map,
        )


def main() -> None:
    get_settings()
    with SessionLocal() as db:
        for index, (question_id, question) in enumerate(QUESTIONS):
            if index:
                print()
            _run_question(db, question_id, question)


if __name__ == "__main__":
    try:
        main()
    except LocalLLMError:
        print("Ollama status: unavailable")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Diagnostic status: unavailable ({type(exc).__name__})")

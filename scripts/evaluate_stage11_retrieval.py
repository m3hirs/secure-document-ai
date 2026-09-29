"""Read-only, privacy-safe Stage 11 retrieval evaluation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import SessionLocal
from app.services.entity_presence_service import resolve_authorized_named_target
from app.services.llm_service import LocalLLMError
from app.services.rag_service import (
    answer_question,
    classify_rag_intent,
    retrieve_authorized_passages,
)


RESTRICTED_DOCUMENT_ID = 35
TOP_K = 5


@dataclass(frozen=True)
class EvaluationCase:
    label: str
    query: str
    expected_document_ids: frozenset[int]
    expected_intent: str
    should_answer: bool
    expected_insufficient_evidence: bool
    ollama_expected: bool


CASES = (
    EvaluationCase(
        "N1",
        "summary of enterprise document one",
        frozenset({1}),
        "named_document",
        True,
        False,
        True,
    ),
    EvaluationCase(
        "N2",
        "what is in Enterprise_Document_01.pdf",
        frozenset({1}),
        "named_document",
        True,
        False,
        True,
    ),
    EvaluationCase(
        "N3",
        "technologies in Aarav Mehta resume",
        frozenset({39}),
        "named_document",
        True,
        False,
        True,
    ),
    EvaluationCase(
        "R1",
        "responsible AI monitoring",
        frozenset({31, 39}),
        "general",
        True,
        False,
        True,
    ),
    EvaluationCase(
        "Z1",
        "quantum banana farming satellite recipe",
        frozenset(),
        "general",
        False,
        True,
        False,
    ),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate authorized Stage 11 retrieval without printing content."
    )
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument(
        "--with-ollama",
        action="store_true",
        help="Also execute production answer generation for answerable cases.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    correct_binding = 0
    named_total = 0
    named_correct = 0
    answerability_correct = 0
    insufficient_classification_correct = 0
    irrelevant_documents = 0
    returned_documents = 0
    unauthorized_leakage = 0

    with SessionLocal() as db:
        for case in CASES:
            intent = classify_rag_intent(case.query)
            document_ids = None
            bound_document_ids: set[int] = set()
            ambiguous = False
            if intent.kind == "named_document":
                named_total += 1
                resolution = resolve_authorized_named_target(
                    db,
                    arguments.user_id,
                    intent.entity or "",
                )
                document_ids = resolution.document_ids
                bound_document_ids = set(document_ids)
                ambiguous = resolution.ambiguous
                if not document_ids:
                    passages = []
                else:
                    passages = retrieve_authorized_passages(
                        db,
                        arguments.user_id,
                        case.query,
                        TOP_K,
                        document_ids=document_ids,
                    )
            else:
                passages = retrieve_authorized_passages(
                    db,
                    arguments.user_id,
                    case.query,
                    TOP_K,
                )

            retrieved_ids = {passage.document_id for passage in passages}
            evaluated_ids = (
                bound_document_ids
                if intent.kind == "named_document"
                else retrieved_ids
            )
            leaked = RESTRICTED_DOCUMENT_ID in retrieved_ids | bound_document_ids
            unauthorized_leakage += int(leaked)
            binding_ok = evaluated_ids == case.expected_document_ids
            correct_binding += int(binding_ok)
            if intent.kind == "named_document":
                named_correct += int(binding_ok and not ambiguous)
            observed_answerable = bool(passages) and not ambiguous
            answerability_correct += int(observed_answerable == case.should_answer)
            returned_documents += len(evaluated_ids)
            irrelevant_documents += len(evaluated_ids - case.expected_document_ids)

            actual_insufficient = not observed_answerable
            actual_ollama_called = False
            if arguments.with_ollama and observed_answerable:
                try:
                    result = answer_question(
                        db,
                        arguments.user_id,
                        case.query,
                        TOP_K,
                    )
                except LocalLLMError:
                    print(f"{case.label}: local Ollama unavailable")
                    return 2
                actual_insufficient = result.insufficient_evidence
                actual_ollama_called = intent.kind not in {
                    "entity_count",
                    "entity_presence",
                }
                if RESTRICTED_DOCUMENT_ID in {
                    source.document_id for source in result.sources
                }:
                    unauthorized_leakage += 1
                    leaked = True

            insufficient_ok = (
                actual_insufficient == case.expected_insufficient_evidence
            )
            insufficient_classification_correct += int(insufficient_ok)

            print(
                f"{case.label}: intent={intent.kind}; bound_documents={sorted(bound_document_ids)}; "
                f"retrieved_documents={sorted(retrieved_ids)}; "
                f"binding_ok={binding_ok}; ambiguous={ambiguous}; "
                f"should_answer={case.should_answer}; "
                f"insufficient_evidence={actual_insufficient}; "
                f"insufficient_ok={insufficient_ok}; "
                f"ollama_expected={case.ollama_expected}; "
                f"ollama_called={actual_ollama_called}; leakage={leaked}"
            )

    case_count = len(CASES)
    irrelevant_rate = (
        irrelevant_documents / returned_documents if returned_documents else 0.0
    )
    print(f"correct_document_binding={correct_binding}/{case_count}")
    print(f"named_document_accuracy={named_correct}/{named_total}")
    print(f"answerability_accuracy={answerability_correct}/{case_count}")
    print(
        "insufficient_evidence_accuracy="
        f"{insufficient_classification_correct}/{case_count}"
    )
    print(f"irrelevant_retrieval_rate={irrelevant_rate:.3f}")
    print(f"unauthorized_leakage={unauthorized_leakage}")
    return 1 if unauthorized_leakage else 0


if __name__ == "__main__":
    raise SystemExit(main())

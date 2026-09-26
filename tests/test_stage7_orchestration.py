from unittest.mock import Mock, patch

import pytest

from app.schemas.rag import RagSourceRead
from app.services.llm_service import LocalLLMError
from app.services.rag_service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    RagContext,
    answer_question,
    classify_question_category,
)


QUESTION = "What local processing control is required?"
CATEGORY_QUESTION = "What programming languages are listed?"


def _source(source_id: str, document_id: int = 7, chunk_id: int = 11) -> RagSourceRead:
    return RagSourceRead(
        source_id=source_id,
        document_id=document_id,
        filename=f"authorized-{document_id}.pdf",
        page_number=2,
        chunk_id=chunk_id,
        snippet=f"Authorized passage {source_id}.",
        similarity=0.9,
    )


def _context(*sources: RagSourceRead) -> RagContext:
    return RagContext("[Source S1] authorized context", list(sources))


def _categorized_source(
    source_id: str,
    snippet: str,
    document_id: int,
    page_number: int,
    chunk_id: int,
) -> RagSourceRead:
    return RagSourceRead(
        source_id=source_id,
        document_id=document_id,
        filename=f"authorized-{document_id}.pdf",
        page_number=page_number,
        chunk_id=chunk_id,
        snippet=snippet,
        similarity=0.9,
    )


def _categorized_sources() -> list[RagSourceRead]:
    return [
        _categorized_source(
            "S1", "Languages: Python, Java", 10, 1, 101
        ),
        _categorized_source(
            "S2", "Frameworks: TensorFlow, PyTorch", 11, 2, 102
        ),
        _categorized_source(
            "S3", "Databases: PostgreSQL", 12, 3, 103
        ),
        _categorized_source(
            "S4", "Tools: Git", 13, 4, 104
        ),
    ]


def test_valid_structured_answer_uses_trusted_identity_and_single_source():
    source = _source("S1")
    db = Mock()
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[source]) as retrieve,
        patch("app.services.rag_service.select_rag_context", return_value=_context(source)),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Local processing is required.", "source_ids": ["S1"]},
        ) as generate,
    ):
        result = answer_question(db, 42, QUESTION, 3)

    retrieve.assert_called_once_with(db=db, user_id=42, question=QUESTION, top_k=3)
    generate.assert_called_once_with(QUESTION, "[Source S1] authorized context", ["S1"])
    assert result.sources == [source]
    assert result.insufficient_evidence is False


def test_multiple_source_ids_return_sources_in_selected_order():
    first = _source("S1")
    second = _source("S2", document_id=8, chunk_id=12)
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[first, second]),
        patch("app.services.rag_service.select_rag_context", return_value=_context(first, second)),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Supported answer.", "source_ids": ["S2", "S1"]},
        ),
    ):
        result = answer_question(Mock(), 42, QUESTION)

    assert result.sources == [first, second]


@pytest.mark.parametrize(
    "passages,context",
    [([], RagContext("", [])), ([_source("S1")], RagContext("", []))],
)
def test_empty_retrieval_or_oversized_context_never_calls_ollama(passages, context):
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=passages),
        patch("app.services.rag_service.select_rag_context", return_value=context),
        patch("app.services.rag_service.generate_local_structured_answer") as generate,
    ):
        result = answer_question(Mock(), 42, QUESTION)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    generate.assert_not_called()


def test_exact_insufficient_evidence_answer_returns_no_sources():
    source = _source("S1")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[source]),
        patch("app.services.rag_service.select_rag_context", return_value=_context(source)),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": INSUFFICIENT_EVIDENCE_ANSWER, "source_ids": []},
        ),
    ):
        result = answer_question(Mock(), 42, QUESTION)

    assert result.insufficient_evidence is True
    assert result.sources == []


@pytest.mark.parametrize(
    "model_output",
    [
        None,
        {"answer": ["wrong"], "source_ids": ["S1"]},
        {"answer": "Supported.", "source_ids": [1]},
        {"answer": "Supported.", "source_ids": ["S1", "S1"]},
        {"answer": "Supported.", "source_ids": ["S99"]},
        {"answer": "Supported.", "source_ids": []},
        {"answer": "Supported.", "source_ids": ["S1"], "extra": True},
        {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "source_ids": ["S1"]},
    ],
)
def test_malformed_or_untrusted_structured_output_fails_closed(model_output):
    source = _source("S1")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[source]),
        patch("app.services.rag_service.select_rag_context", return_value=_context(source)),
        patch("app.services.rag_service.generate_local_structured_answer", return_value=model_output),
    ):
        result = answer_question(Mock(), 42, QUESTION)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True


def test_model_source_ids_cannot_alter_python_source_metadata():
    source = _source("S1", document_id=7, chunk_id=11)
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[source]),
        patch("app.services.rag_service.select_rag_context", return_value=_context(source)),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            return_value={"answer": "Supported answer.", "source_ids": ["S1"]},
        ),
    ):
        result = answer_question(Mock(), 42, QUESTION)

    assert result.sources[0].filename == "authorized-7.pdf"
    assert result.sources[0].page_number == 2
    assert result.sources[0].chunk_id == 11


def test_unauthorized_document_empty_retrieval_never_reaches_ollama():
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[]),
        patch("app.services.rag_service.select_rag_context", return_value=RagContext("", [])),
        patch("app.services.rag_service.generate_local_structured_answer") as generate,
    ):
        answer_question(Mock(), 42, QUESTION)

    generate.assert_not_called()


def test_local_llm_error_propagates_without_retry():
    source = _source("S1")
    with (
        patch("app.services.rag_service.retrieve_authorized_passages", return_value=[source]),
        patch("app.services.rag_service.select_rag_context", return_value=_context(source)),
        patch(
            "app.services.rag_service.generate_local_structured_answer",
            side_effect=LocalLLMError("unavailable"),
        ) as generate,
    ):
        with pytest.raises(LocalLLMError):
            answer_question(Mock(), 42, QUESTION)

    generate.assert_called_once()


@pytest.mark.parametrize(
    ("question", "top_k"),
    [(" ", 5), ("Q" * 1001, 5), (QUESTION, 0), (QUESTION, 11)],
)
def test_invalid_question_or_top_k_is_rejected_at_service_boundary(question: str, top_k: int):
    with patch("app.services.rag_service.retrieve_authorized_passages") as retrieve:
        with pytest.raises(ValueError):
            answer_question(Mock(), 42, question, top_k)

    retrieve.assert_not_called()


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (CATEGORY_QUESTION, "programming_language"),
        (
            "Which machine learning frameworks and libraries are used?",
            "ml_framework_or_library",
        ),
        ("Which databases are listed?", "database"),
        (
            "Which infrastructure tools are used?",
            "infrastructure_platform",
        ),
        ("Which APIs are mentioned?", "api_technology"),
        ("What languages are spoken?", None),
        ("What technologies are used?", None),
        (
            "Which programming languages and databases are listed?",
            None,
        ),
        ("How does the monitoring platform work?", None),
        ("Which tools are listed?", None),
    ],
)
def test_question_category_classifier(question: str, expected: str | None):
    assert classify_question_category(question) == expected


def test_category_answer_prunes_mixed_items_and_unneeded_sources():
    sources = _categorized_sources()
    context = RagContext("authorized categorized context", sources)
    model_output = {
        "answer_items": [
            {
                "text": "Python",
                "category": "programming_language",
                "source_ids": ["S1"],
            },
            {
                "text": "Java",
                "category": "programming_language",
                "source_ids": ["S1"],
            },
            {
                "text": "TensorFlow",
                "category": "ml_framework_or_library",
                "source_ids": ["S2"],
            },
            {
                "text": "PyTorch",
                "category": "ml_framework_or_library",
                "source_ids": ["S2"],
            },
            {
                "text": "PostgreSQL",
                "category": "database",
                "source_ids": ["S3"],
            },
            {
                "text": "Git",
                "category": "infrastructure_platform",
                "source_ids": ["S4"],
            },
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=sources,
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=context,
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ) as categorized_generate,
        patch(
            "app.services.rag_service.generate_local_structured_answer",
        ) as general_generate,
    ):
        result = answer_question(Mock(), 42, CATEGORY_QUESTION)

    assert result.answer == "Python and Java."
    assert "TensorFlow" not in result.answer
    assert "PyTorch" not in result.answer
    assert "PostgreSQL" not in result.answer
    assert "Git" not in result.answer
    assert result.sources == [sources[0]]
    assert result.sources[0].document_id == 10
    assert result.sources[0].filename == "authorized-10.pdf"
    assert result.sources[0].page_number == 1
    assert result.sources[0].chunk_id == 101
    assert result.insufficient_evidence is False
    categorized_generate.assert_called_once_with(
        CATEGORY_QUESTION,
        "authorized categorized context",
        "programming_language",
        ["S1", "S2", "S3", "S4"],
    )
    general_generate.assert_not_called()


def test_mislabeled_framework_is_not_accepted_as_programming_language():
    sources = _categorized_sources()
    context = RagContext("authorized categorized context", sources)
    model_output = {
        "answer_items": [
            {
                "text": "Python",
                "category": "programming_language",
                "source_ids": ["S1"],
            },
            {
                "text": "TensorFlow",
                "category": "programming_language",
                "source_ids": ["S2"],
            },
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=sources,
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=context,
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(Mock(), 42, CATEGORY_QUESTION)

    assert result.answer == "Python."
    assert result.sources == [sources[0]]


def test_categorized_answer_with_unauthorized_source_id_fails_closed():
    sources = _categorized_sources()
    context = RagContext("authorized categorized context", sources)
    model_output = {
        "answer_items": [
            {
                "text": "Python",
                "category": "programming_language",
                "source_ids": ["S99"],
            }
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=sources,
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=context,
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(Mock(), 42, CATEGORY_QUESTION)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True


def test_all_rejected_category_items_return_insufficient_evidence():
    sources = _categorized_sources()
    context = RagContext("authorized categorized context", sources)
    model_output = {
        "answer_items": [
            {
                "text": "TensorFlow",
                "category": "ml_framework_or_library",
                "source_ids": ["S2"],
            },
            {
                "text": "PostgreSQL",
                "category": "database",
                "source_ids": ["S3"],
            },
            {
                "text": "Git",
                "category": "infrastructure_platform",
                "source_ids": ["S4"],
            },
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=sources,
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=context,
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ) as categorized_generate,
    ):
        result = answer_question(Mock(), 42, CATEGORY_QUESTION)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True
    categorized_generate.assert_called_once()


def test_combined_database_tools_heading_keeps_only_databases():
    source = _categorized_source(
        "S1",
        "Databases Tools: PostgreSQL, MySQL, Redis, Postman, Linux, VS Code",
        20,
        1,
        201,
    )
    model_output = {
        "answer_items": [
            {
                "text": item,
                "category": "database",
                "source_ids": ["S1"],
            }
            for item in (
                "PostgreSQL",
                "MySQL",
                "Redis",
                "Postman",
                "Linux",
                "VS Code",
            )
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=[source],
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=RagContext("authorized database context", [source]),
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(
            Mock(),
            42,
            "Which databases are listed?",
        )

    assert result.answer == "PostgreSQL, MySQL, and Redis."
    assert result.sources == [source]


def test_explicit_project_roles_support_infrastructure_items():
    source = _categorized_source(
        "S1",
        "Kafka-based asynchronous messaging architecture. Kubernetes cluster.",
        21,
        2,
        202,
    )
    model_output = {
        "answer_items": [
            {
                "text": "Kafka",
                "category": "infrastructure_platform",
                "source_ids": ["S1"],
            },
            {
                "text": "Kubernetes",
                "category": "infrastructure_platform",
                "source_ids": ["S1"],
            },
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=[source],
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=RagContext("authorized infrastructure context", [source]),
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(
            Mock(),
            42,
            "Which infrastructure technologies are used?",
        )

    assert result.answer == "Kafka and Kubernetes."
    assert result.sources == [source]


def test_labeled_technical_section_keeps_only_explicit_api_items():
    source = _categorized_source(
        "S1",
        "Core Technologies: REST APIs, 6 API modules, FastAPI web framework, Git",
        22,
        3,
        203,
    )
    model_output = {
        "answer_items": [
            {
                "text": "REST APIs",
                "category": "api_technology",
                "source_ids": ["S1"],
            },
            {
                "text": "API modules",
                "category": "api_technology",
                "source_ids": ["S1"],
            },
            {
                "text": "FastAPI",
                "category": "api_technology",
                "source_ids": ["S1"],
            },
            {
                "text": "Git",
                "category": "api_technology",
                "source_ids": ["S1"],
            },
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=[source],
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=RagContext("authorized API context", [source]),
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(
            Mock(),
            42,
            "Which API technologies are listed?",
        )

    assert result.answer == "REST APIs, API modules, and FastAPI."
    assert result.sources == [source]


def test_core_cs_concepts_keeps_only_literal_api_items():
    source = _categorized_source(
        "S1",
        (
            "Core CS Concepts: DBMS, Operating Systems, REST APIs, "
            "Microservices Architecture, System Design"
        ),
        24,
        5,
        205,
    )
    model_output = {
        "answer_items": [
            {
                "text": item,
                "category": "api_technology",
                "source_ids": ["S1"],
            }
            for item in (
                "REST APIs",
                "DBMS",
                "Operating Systems",
                "Microservices Architecture",
                "System Design",
            )
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=[source],
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=RagContext("authorized API context", [source]),
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(
            Mock(),
            42,
            "Which API technologies are listed?",
        )

    assert result.answer == "REST APIs."
    assert result.sources == [source]
    assert result.insufficient_evidence is False


@pytest.mark.parametrize(
    ("question", "category"),
    [
        ("What programming languages are listed?", "programming_language"),
        ("Which databases are listed?", "database"),
        ("Which APIs are listed?", "api_technology"),
    ],
)
def test_generic_tools_git_is_not_reclassified(question: str, category: str):
    source = _categorized_source(
        "S1",
        "Tools: Git",
        23,
        4,
        204,
    )
    model_output = {
        "answer_items": [
            {
                "text": "Git",
                "category": category,
                "source_ids": ["S1"],
            }
        ]
    }

    with (
        patch(
            "app.services.rag_service.retrieve_authorized_passages",
            return_value=[source],
        ),
        patch(
            "app.services.rag_service.select_rag_context",
            return_value=RagContext("authorized tools context", [source]),
        ),
        patch(
            "app.services.rag_service.generate_local_categorized_answer",
            return_value=model_output,
        ),
    ):
        result = answer_question(Mock(), 42, question)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.sources == []
    assert result.insufficient_evidence is True

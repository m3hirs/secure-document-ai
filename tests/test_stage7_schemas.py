import pytest
from pydantic import ValidationError

from app.schemas.rag import RagAnswerRead, RagQuestionRequest


def test_question_uses_default_top_k():
    request = RagQuestionRequest(question="What does the architecture describe?")

    assert request.question == "What does the architecture describe?"
    assert request.top_k == 5


def test_question_accepts_valid_custom_top_k():
    request = RagQuestionRequest(question="Which controls are required?", top_k=10)

    assert request.top_k == 10


@pytest.mark.parametrize("question", ["", "   \t\n"])
def test_question_rejects_empty_or_whitespace_only_values(question: str):
    with pytest.raises(ValidationError):
        RagQuestionRequest(question=question)


def test_question_rejects_values_longer_than_one_thousand_characters():
    with pytest.raises(ValidationError):
        RagQuestionRequest(question="a" * 1001)


@pytest.mark.parametrize("top_k", [0, 11])
def test_question_enforces_top_k_range(top_k: int):
    with pytest.raises(ValidationError):
        RagQuestionRequest(question="What is covered?", top_k=top_k)


def test_question_rejects_client_supplied_user_id():
    with pytest.raises(ValidationError):
        RagQuestionRequest(question="What is covered?", user_id=42)


def test_answer_accepts_verified_source_records():
    answer = RagAnswerRead(
        answer="The architecture requires local processing [S1].",
        sources=[
            {
                "source_id": "S1",
                "document_id": 8,
                "filename": "architecture.pdf",
                "page_number": 3,
                "chunk_id": 41,
                "snippet": "All confidential processing remains local.",
                "similarity": 0.91,
            }
        ],
        model="qwen2.5:1.5b",
        insufficient_evidence=False,
    )

    assert answer.sources[0].source_id == "S1"
    assert answer.sources[0].page_number == 3

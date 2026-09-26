"""Schemas for authorization-aware local document question answering."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RagQuestionRequest(BaseModel):
    """A question to answer from passages the current principal may access."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="Question to answer using authorized document passages.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of authorized passages to retrieve.",
    )

    @field_validator("question")
    @classmethod
    def question_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be empty or whitespace-only")
        return value


class RagSourceRead(BaseModel):
    """An authorized retrieved passage cited by a RAG answer."""

    source_id: str = Field(description='Application-assigned reference, such as "S1".')
    document_id: int
    filename: str
    page_number: int
    chunk_id: int
    snippet: str
    similarity: float


class RagAnswerRead(BaseModel):
    """A locally generated answer and its authorized supporting sources."""

    answer: str
    sources: list[RagSourceRead]
    model: str
    insufficient_evidence: bool

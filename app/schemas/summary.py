"""Response schemas for local document summarization."""

from pydantic import BaseModel


class DocumentSummaryRead(BaseModel):
    document_id: int
    filename: str
    summary: str
    model: str
    source_characters: int
    truncated: bool
"""API endpoints for local document summarization."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.schemas.summary import DocumentSummaryRead
from app.services.llm_service import LocalLLMError
from app.services.summarization_service import summarize_document


router = APIRouter(tags=["summaries"])


@router.post(
    "/documents/{document_id}/summarize",
    response_model=DocumentSummaryRead,
)
def summarize_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        return summarize_document(
            db=db,
            document_id=document_id,
            user_id=principal.user_id,
        )
    except LocalLLMError:
        raise HTTPException(
            status_code=503,
            detail="Local summarization service is unavailable",
        ) from None
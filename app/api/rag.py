"""Authenticated API endpoint for local, authorization-aware RAG answers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.schemas.rag import RagAnswerRead, RagQuestionRequest
from app.services.llm_service import LocalLLMError
from app.services.rag_service import answer_question


router = APIRouter(tags=["rag"])


@router.post("/documents/ask", response_model=RagAnswerRead)
def ask_documents(
    payload: RagQuestionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RagAnswerRead:
    """Answer using passages authorized for the trusted current principal."""
    try:
        return answer_question(
            db=db,
            user_id=principal.user_id,
            question=payload.question,
            top_k=payload.top_k,
        )
    except LocalLLMError:
        raise HTTPException(
            status_code=503,
            detail="Local AI service is temporarily unavailable.",
        ) from None

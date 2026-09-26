from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.schemas.search import DocumentSearchRequest, DocumentSearchResponse, SemanticSearchRequest, SemanticSearchResponse
from app.services.document_search_service import search_documents as search_document_results
from app.services.natural_search_parser import parse_query
from app.services.semantic_search_service import semantic_search

router = APIRouter(tags=["search"])

@router.post("/search/semantic", response_model=SemanticSearchResponse)
def search_documents(payload: SemanticSearchRequest, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    settings = get_settings()
    if payload.top_k is not None and payload.top_k > settings.semantic_search_max_top_k:
        raise HTTPException(422, "top_k exceeds configured maximum")
    results = semantic_search(db, principal.user_id, payload.query, payload.top_k)
    return {"results": results, "message": None if results else "No accessible matching documents found."}

@router.post("/search/documents", response_model=DocumentSearchResponse)
def natural_document_search(payload:DocumentSearchRequest, db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
    settings=get_settings()
    if payload.page_size>settings.semantic_search_max_top_k: raise HTTPException(422,"page_size exceeds configured maximum")
    parsed=parse_query(db,payload.query,principal.user_id,settings.app_timezone)
    rows=search_document_results(db,principal.user_id,parsed,payload.page,payload.page_size)
    results=[]
    for document,chunk_id,page_number,semantic in rows:
        text,score=semantic if semantic else (None,None)
        results.append({"document_id":document.id,"filename":document.filename,"classification":document.classification.name if document.classification else None,"uploaded_at":document.uploaded_at,"uploader_name":document.uploader.name if document.uploader else None,"file_type":document.file_type,"page_number":page_number,"chunk_id":chunk_id,"snippet":text,"similarity_score":score})
    filters={key:value for key,value in {"file_type":parsed.file_type,"uploader_id":parsed.uploader_id,"team_id":parsed.team_id,"classification_id":parsed.classification_id,"tag_id":parsed.tag_id,"uploaded_after":parsed.start,"uploaded_before":parsed.end}.items() if value is not None}
    return {"mode":parsed.mode,"applied_filters":filters,"results":results,"page":payload.page,"page_size":payload.page_size,"total_returned":len(results),"message":None if results else "No accessible matching documents found."}

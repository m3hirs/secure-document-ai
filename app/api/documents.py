from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.db.database import get_db
from app.db.models import Classification, Document, DocumentChunk, DocumentEvent, DocumentPage, Team, User, user_teams
from app.core.security import Principal, get_current_principal, require_csrf_protection
from app.schemas.document import ChunkingRead, DocumentChunkRead, DocumentPageRead, DocumentRead, EmbeddingRead, ProcessingRead
from app.services.chunking_service import rechunk_document
from app.services.embedding_service import embed_document
from app.services.pdf_service import process_pdf
from app.services.semantic_search_service import accessible_document, document_accessible_clause
from app.services.storage_service import save_pdf, storage_directory
router=APIRouter(tags=["documents"])
loads=(selectinload(Document.tags),selectinload(Document.teams),selectinload(Document.classification),selectinload(Document.uploader))

def _processing_response(document: Document) -> dict:
 return {"document_id":document.id,"filename":document.filename,"processing_status":document.processing_status,"page_count":document.page_count,"extracted_text_length":document.extracted_text_length,"text_page_count":document.text_page_count,"image_count":document.image_count,"ocr_page_count":document.ocr_page_count,"processing_started_at":document.processing_started_at,"processed_at":document.processed_at,"processing_error":document.processing_error}

def _chunking_response(document: Document) -> dict:
 return {"document_id":document.id,"filename":document.filename,"chunking_status":document.chunking_status,"chunk_count":document.chunk_count,"chunking_version":document.chunking_version,"chunked_at":document.chunked_at,"chunking_error":document.chunking_error}

def _embedding_response(document: Document) -> dict:
 return {"document_id":document.id,"filename":document.filename,"embedding_status":document.embedding_status,"embedding_count":document.embedding_count,"embedding_version":document.embedding_version,"embedded_at":document.embedded_at,"embedding_error":document.embedding_error}

def _parse_team_ids(team_ids: str | None) -> list[int]:
 if not team_ids: return []
 try: return list({int(value.strip()) for value in team_ids.split(",") if value.strip()})
 except ValueError: raise HTTPException(422,"team_ids must be a comma-separated list of integers")

def _upload_one(file: UploadFile, classification_id: int, uploaded_by: int, team_ids: list[int], db: Session) -> Document:
 if not file.filename or Path(file.filename).suffix.lower() != ".pdf": raise HTTPException(415,"Only PDF files are accepted")
 classification=db.get(Classification,classification_id); uploader=db.get(User,uploaded_by)
 if not classification: raise HTTPException(404,"Classification not found")
 if not uploader: raise HTTPException(404,"Uploader not found")
 teams=list(db.scalars(select(Team).where(Team.id.in_(team_ids)))) if team_ids else []
 if len(teams)!=len(team_ids): raise HTTPException(404,"One or more teams were not found")
 if team_ids:
  allowed_teams=set(db.scalars(select(user_teams.c.team_id).where(user_teams.c.user_id==uploaded_by)))
  if not set(team_ids).issubset(allowed_teams): raise HTTPException(403,"Cannot assign documents to teams outside your membership")
 try: stored_name,size=save_pdf(file)
 except ValueError as exc: raise HTTPException(415,str(exc))
 document=Document(filename=Path(file.filename).name,file_path=stored_name,file_type="application/pdf",file_size=size,classification=classification,uploader=uploader,uploaded_at=datetime.now(timezone.utc),teams=teams)
 db.add(document); db.flush(); db.add(DocumentEvent(document=document,user_id=uploader.id,event_type="uploaded",event_metadata={"source":"api"})); db.commit(); db.refresh(document)
 return process_pdf(db,document,storage_directory()/stored_name)

@router.post("/documents/upload",response_model=ProcessingRead,status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile=File(...), classification_id: int=Form(...), team_ids: str|None=Form(None), db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal), _csrf:None=Depends(require_csrf_protection)):
 return _processing_response(_upload_one(file,classification_id,principal.user_id,_parse_team_ids(team_ids),db))

@router.post("/documents/upload-bulk",response_model=list[ProcessingRead],status_code=status.HTTP_201_CREATED)
def upload_documents_bulk(files: list[UploadFile]=File(...), classification_id: int=Form(...), team_ids: str|None=Form(None), db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal), _csrf:None=Depends(require_csrf_protection)):
 results=[]
 for file in files:
  try: results.append(_processing_response(_upload_one(file,classification_id,principal.user_id,_parse_team_ids(team_ids),db)))
  except HTTPException as exc: results.append({"document_id":0,"filename":Path(file.filename or "unknown").name,"processing_status":"failed","page_count":None,"extracted_text_length":0,"text_page_count":0,"image_count":0,"ocr_page_count":0,"processing_started_at":None,"processed_at":None,"processing_error":exc.detail})
 return results
@router.get("/documents",response_model=list[DocumentRead])
def list_documents(db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)): return list(db.scalars(select(Document).options(*loads).where(document_accessible_clause(principal.user_id)).order_by(Document.uploaded_at.desc())))
@router.get("/documents/{document_id}",response_model=DocumentRead)
def get_document(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 document=db.scalar(select(Document).options(*loads).where(Document.id==document_id,document_accessible_clause(principal.user_id)))
 if not document: raise HTTPException(404,"Document not found")
 return document

@router.get("/documents/{document_id}/processing",response_model=ProcessingRead)
def get_processing(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 document=accessible_document(db,document_id,principal.user_id)
 if not document: raise HTTPException(404,"Document not found")
 return _processing_response(document)

@router.get("/documents/{document_id}/pages",response_model=list[DocumentPageRead])
def get_document_pages(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 if not accessible_document(db,document_id,principal.user_id): raise HTTPException(404,"Document not found")
 return list(db.scalars(select(DocumentPage).where(DocumentPage.document_id==document_id).order_by(DocumentPage.page_number)))

@router.get("/documents/{document_id}/chunking",response_model=ChunkingRead)
def get_chunking(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 document=accessible_document(db,document_id,principal.user_id)
 if not document: raise HTTPException(404,"Document not found")
 return _chunking_response(document)

@router.get("/documents/{document_id}/chunks",response_model=list[DocumentChunkRead])
def get_document_chunks(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 if not accessible_document(db,document_id,principal.user_id): raise HTTPException(404,"Document not found")
 chunks=db.scalars(select(DocumentChunk).join(DocumentPage).where(DocumentChunk.document_id==document_id).order_by(DocumentPage.page_number,DocumentChunk.chunk_index)).all()
 return [{"id":chunk.id,"document_id":chunk.document_id,"page_id":chunk.page_id,"page_number":chunk.page.page_number,"chunk_index":chunk.chunk_index,"text":chunk.text,"character_count":chunk.character_count,"token_count":chunk.token_count,"source_start_char":chunk.source_start_char,"source_end_char":chunk.source_end_char,"chunk_metadata":chunk.chunk_metadata,"created_at":chunk.created_at} for chunk in chunks]

@router.post("/documents/{document_id}/rechunk",response_model=ChunkingRead)
def rechunk(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal), _csrf:None=Depends(require_csrf_protection)):
 document=accessible_document(db,document_id,principal.user_id)
 if not document: raise HTTPException(404,"Document not found")
 return _chunking_response(rechunk_document(db,document))

@router.post("/documents/{document_id}/embed",response_model=EmbeddingRead)
def embed(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal), _csrf:None=Depends(require_csrf_protection)):
 document=accessible_document(db,document_id,principal.user_id)
 if not document: raise HTTPException(404,"Document not found")
 return _embedding_response(embed_document(db,document))

@router.get("/documents/{document_id}/embedding",response_model=EmbeddingRead)
def get_embedding(document_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 document=accessible_document(db,document_id,principal.user_id)
 if not document: raise HTTPException(404,"Document not found")
 return _embedding_response(document)

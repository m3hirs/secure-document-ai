from datetime import timezone
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session
from app.db.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentPage, document_tags, document_teams
from app.services.embedding_service import embed_query
from app.services.natural_search_parser import ParsedSearch
from app.services.semantic_search_service import document_accessible_clause
from app.core.config import get_settings

def _filters(parsed: ParsedSearch):
    clauses=[]
    if parsed.file_type: clauses.append(Document.file_type==parsed.file_type)
    if parsed.uploader_id: clauses.append(Document.uploaded_by==parsed.uploader_id)
    if parsed.team_id: clauses.append(exists(select(1).where(document_teams.c.document_id==Document.id,document_teams.c.team_id==parsed.team_id)))
    if parsed.tag_id: clauses.append(exists(select(1).where(document_tags.c.document_id==Document.id,document_tags.c.tag_id==parsed.tag_id)))
    if parsed.classification_id: clauses.append(Document.classification_id==parsed.classification_id)
    if parsed.start: clauses.append(Document.uploaded_at>=parsed.start.astimezone(timezone.utc))
    if parsed.end: clauses.append(Document.uploaded_at<parsed.end.astimezone(timezone.utc))
    return clauses

def search_documents(db:Session,user_id:int,parsed:ParsedSearch,page:int,page_size:int):
    base=[document_accessible_clause(user_id),*_filters(parsed)]; offset=(page-1)*page_size
    if parsed.mode=="metadata":
        rows=db.scalars(select(Document).where(*base).order_by(Document.uploaded_at.desc(),Document.id.desc()).offset(offset).limit(page_size)).all()
        return [(d,None,None,None) for d in rows]
    settings=get_settings(); distance=DocumentChunkEmbedding.embedding.cosine_distance(embed_query(parsed.topic or "")).label("distance")
    ranked=select(Document.id.label("document_id"),DocumentChunk.id.label("chunk_id"),DocumentPage.page_number.label("page_number"),DocumentChunk.text.label("text"),distance.label("distance"),func.row_number().over(partition_by=Document.id,order_by=(distance,DocumentChunk.id)).label("rank")).join(DocumentChunk,DocumentChunkEmbedding.chunk_id==DocumentChunk.id).join(Document,DocumentChunk.document_id==Document.id).join(DocumentPage,DocumentChunk.page_id==DocumentPage.id).where(*base,DocumentChunkEmbedding.embedding_version==settings.embedding_version).subquery()
    rows=db.execute(select(Document,ranked.c.chunk_id,ranked.c.page_number,ranked.c.text,ranked.c.distance).join(ranked,ranked.c.document_id==Document.id).where(ranked.c.rank==1).order_by(ranked.c.distance,Document.id).offset(offset).limit(page_size)).all()
    return [(d,chunk_id,page_number,(text,float(1-distance))) for d,chunk_id,page_number,text,distance in rows]

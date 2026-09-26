from datetime import datetime
from pydantic import BaseModel, ConfigDict
class NamedEntity(BaseModel):
 model_config=ConfigDict(from_attributes=True); id:int; name:str
class DocumentRead(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 id:int; filename:str; file_type:str; file_size:int; page_count:int|None; uploaded_at:datetime; created_at:datetime; classification:NamedEntity; uploader:NamedEntity; tags:list[NamedEntity]=[]; teams:list[NamedEntity]=[]

class ProcessingRead(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 document_id:int; filename:str; processing_status:str; page_count:int|None; extracted_text_length:int; text_page_count:int; image_count:int; ocr_page_count:int; processing_started_at:datetime|None; processed_at:datetime|None; processing_error:str|None

class DocumentPageRead(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 page_number:int; extracted_text:str|None; has_text:bool; image_count:int; ocr_used:bool

class ChunkingRead(BaseModel):
 document_id:int; filename:str; chunking_status:str; chunk_count:int; chunking_version:str|None; chunked_at:datetime|None; chunking_error:str|None

class DocumentChunkRead(BaseModel):
 id:int; document_id:int; page_id:int; page_number:int; chunk_index:int; text:str; character_count:int; token_count:int|None; source_start_char:int; source_end_char:int; chunk_metadata:dict|None; created_at:datetime

class EmbeddingRead(BaseModel):
 document_id:int; filename:str; embedding_status:str; embedding_count:int; embedding_version:str|None; embedded_at:datetime|None; embedding_error:str|None

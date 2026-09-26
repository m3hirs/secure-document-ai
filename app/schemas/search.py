from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1)

class SemanticSearchResult(BaseModel):
    document_id: int
    filename: str
    page_number: int
    chunk_id: int
    chunk_text: str
    similarity_score: float

class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchResult]
    message: str | None = None

class DocumentSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
    sort: str = "relevance"

class DocumentSearchResult(BaseModel):
    document_id:int; filename:str; classification:str|None; uploaded_at:datetime; uploader_name:str|None; file_type:str; page_number:int|None=None; chunk_id:int|None=None; snippet:str|None=None; similarity_score:float|None=None

class DocumentSearchResponse(BaseModel):
    mode:str; applied_filters:dict; results:list[DocumentSearchResult]; page:int; page_size:int; total_returned:int; message:str|None=None

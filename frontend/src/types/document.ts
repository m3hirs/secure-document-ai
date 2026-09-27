export interface NamedEntity {
  id: number;
  name: string;
}

export interface DocumentRead {
  id: number;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  uploaded_at: string;
  created_at: string;
  classification: NamedEntity;
  uploader: NamedEntity;
  tags: NamedEntity[];
  teams: NamedEntity[];
  is_archived: boolean;
}

export interface ProcessingRead {
  document_id: number;
  filename: string;
  processing_status: string;
  page_count: number | null;
  extracted_text_length: number;
  text_page_count: number;
  image_count: number;
  ocr_page_count: number;
  processing_started_at: string | null;
  processed_at: string | null;
  processing_error: string | null;
}

export interface DocumentPageRead {
  page_number: number;
  extracted_text: string | null;
  has_text: boolean;
  image_count: number;
  ocr_used: boolean;
}

export interface ChunkingRead {
  document_id: number;
  filename: string;
  chunking_status: string;
  chunk_count: number;
  chunking_version: string | null;
  chunked_at: string | null;
  chunking_error: string | null;
}

export interface DocumentChunkRead {
  id: number;
  document_id: number;
  page_id: number;
  page_number: number;
  chunk_index: number;
  text: string;
  character_count: number;
  token_count: number | null;
  source_start_char: number;
  source_end_char: number;
  chunk_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface EmbeddingRead {
  document_id: number;
  filename: string;
  embedding_status: string;
  embedding_count: number;
  embedding_version: string | null;
  embedded_at: string | null;
  embedding_error: string | null;
}

export interface DocumentDetails {
  document: DocumentRead;
  processing: ProcessingRead;
  pages: DocumentPageRead[];
  chunks: DocumentChunkRead[];
  chunking: ChunkingRead;
  embedding: EmbeddingRead;
}

export interface UploadOptions {
  classificationId: number;
  teamIds: number[];
}

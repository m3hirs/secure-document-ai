export type SearchMode = "semantic" | "natural";

export interface SemanticSearchResult {
  document_id: number;
  filename: string;
  page_number: number;
  chunk_id: number;
  chunk_text: string;
  similarity_score: number;
}

export interface SemanticSearchResponse {
  results: SemanticSearchResult[];
  message: string | null;
}

export interface DocumentSearchResult {
  document_id: number;
  filename: string;
  classification: string | null;
  uploaded_at: string;
  uploader_name: string | null;
  file_type: string;
  page_number: number | null;
  chunk_id: number | null;
  snippet: string | null;
  similarity_score: number | null;
}

export interface DocumentSearchResponse {
  mode: string;
  applied_filters: Record<string, unknown>;
  results: DocumentSearchResult[];
  page: number;
  page_size: number;
  total_returned: number;
  message: string | null;
}

export type SearchResult = SemanticSearchResult | DocumentSearchResult;

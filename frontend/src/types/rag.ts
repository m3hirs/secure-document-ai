export interface RagQuestionRequest {
  question: string;
  top_k: number;
}

export interface RagSourceRead {
  source_id: string;
  document_id: number;
  filename: string;
  page_number: number;
  chunk_id: number;
  snippet: string;
  similarity: number;
}

export interface RagAnswerRead {
  answer: string;
  sources: RagSourceRead[];
  model: string;
  insufficient_evidence: boolean;
}

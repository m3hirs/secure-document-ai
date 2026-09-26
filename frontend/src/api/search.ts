import type {
  DocumentSearchResponse,
  SemanticSearchResponse,
} from "../types/search";
import { apiRequest } from "./client";

export function semanticSearch(query: string, topK: number, signal?: AbortSignal): Promise<SemanticSearchResponse> {
  return apiRequest<SemanticSearchResponse>("/search/semantic", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK }),
    signal,
  });
}

export function naturalDocumentSearch(
  query: string,
  pageSize: number,
  signal?: AbortSignal,
): Promise<DocumentSearchResponse> {
  return apiRequest<DocumentSearchResponse>("/search/documents", {
    method: "POST",
    body: JSON.stringify({ query, page: 1, page_size: pageSize, sort: "relevance" }),
    signal,
  });
}

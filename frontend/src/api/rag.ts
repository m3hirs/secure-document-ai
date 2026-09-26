import type { RagAnswerRead, RagQuestionRequest } from "../types/rag";
import { apiRequest } from "./client";

export function askDocuments(request: RagQuestionRequest, signal?: AbortSignal): Promise<RagAnswerRead> {
  return apiRequest<RagAnswerRead>("/documents/ask", {
    method: "POST",
    body: JSON.stringify(request),
    signal,
  });
}

import type {
  ChunkingRead,
  DocumentChunkRead,
  DocumentDetails,
  DocumentPageRead,
  DocumentRead,
  EmbeddingRead,
  ProcessingRead,
  UploadOptions,
} from "../types/document";
import { apiRequest } from "./client";

export function listDocuments(options: { includeArchived?: boolean; signal?: AbortSignal } = {}): Promise<DocumentRead[]> {
  const query = options.includeArchived ? "?include_archived=true" : "";
  return apiRequest<DocumentRead[]>(`/documents${query}`, { signal: options.signal });
}

export function listClassifications(signal?: AbortSignal): Promise<{ id: number; name: string }[]> {
  return apiRequest<{ id: number; name: string }[]>("/classifications", { signal });
}

export function listTeams(signal?: AbortSignal): Promise<{ id: number; name: string }[]> {
  return apiRequest<{ id: number; name: string }[]>("/teams", { signal });
}

export function getDocument(documentId: number, signal?: AbortSignal): Promise<DocumentRead> {
  return apiRequest<DocumentRead>(`/documents/${documentId}`, { signal });
}

export function getProcessing(documentId: number, signal?: AbortSignal): Promise<ProcessingRead> {
  return apiRequest<ProcessingRead>(`/documents/${documentId}/processing`, { signal });
}

export function getPages(documentId: number, signal?: AbortSignal): Promise<DocumentPageRead[]> {
  return apiRequest<DocumentPageRead[]>(`/documents/${documentId}/pages`, { signal });
}

export function getChunks(documentId: number, signal?: AbortSignal): Promise<DocumentChunkRead[]> {
  return apiRequest<DocumentChunkRead[]>(`/documents/${documentId}/chunks`, { signal });
}

export function getChunking(documentId: number, signal?: AbortSignal): Promise<ChunkingRead> {
  return apiRequest<ChunkingRead>(`/documents/${documentId}/chunking`, { signal });
}

export function getEmbedding(documentId: number, signal?: AbortSignal): Promise<EmbeddingRead> {
  return apiRequest<EmbeddingRead>(`/documents/${documentId}/embedding`, { signal });
}

export async function getDocumentDetails(documentId: number, signal?: AbortSignal): Promise<DocumentDetails> {
  const [document, processing, pages, chunks, chunking, embedding] = await Promise.all([
    getDocument(documentId, signal),
    getProcessing(documentId, signal),
    getPages(documentId, signal),
    getChunks(documentId, signal),
    getChunking(documentId, signal),
    getEmbedding(documentId, signal),
  ]);
  return { document, processing, pages, chunks, chunking, embedding };
}

function uploadForm(files: File[], options: UploadOptions, fieldName: "file" | "files") {
  const form = new FormData();
  for (const file of files) form.append(fieldName, file);
  form.append("classification_id", String(options.classificationId));
  form.append("team_ids", options.teamIds.join(","));
  return form;
}

export function uploadDocument(
  file: File,
  options: UploadOptions,
  csrfToken: string,
): Promise<ProcessingRead> {
  return apiRequest<ProcessingRead>("/documents/upload", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: uploadForm([file], options, "file"),
  });
}

export function uploadDocuments(
  files: File[],
  options: UploadOptions,
  csrfToken: string,
): Promise<ProcessingRead[]> {
  return apiRequest<ProcessingRead[]>("/documents/upload-bulk", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: uploadForm(files, options, "files"),
  });
}

export function rechunkDocument(documentId: number, csrfToken: string): Promise<ChunkingRead> {
  return apiRequest<ChunkingRead>(`/documents/${documentId}/rechunk`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function embedDocument(documentId: number, csrfToken: string): Promise<EmbeddingRead> {
  return apiRequest<EmbeddingRead>(`/documents/${documentId}/embed`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function archiveDocument(documentId: number, csrfToken: string): Promise<DocumentRead> {
  return apiRequest<DocumentRead>(`/documents/${documentId}/archive`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({}),
  });
}

export function restoreDocument(documentId: number, csrfToken: string): Promise<DocumentRead> {
  return apiRequest<DocumentRead>(`/documents/${documentId}/restore`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({}),
  });
}

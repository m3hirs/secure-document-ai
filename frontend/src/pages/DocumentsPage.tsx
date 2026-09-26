import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import {
  embedDocument,
  getDocumentDetails,
  listClassifications,
  listDocuments,
  rechunkDocument,
  uploadDocument,
  uploadDocuments,
} from "../api/documents";
import { ApiError, isAbortError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import type { DocumentDetails, DocumentRead, ProcessingRead } from "../types/document";

type DetailTab = "overview" | "pages" | "chunks" | "processing";

function formatDate(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusClasses(status: string) {
  const value = status.toLowerCase();
  if (["processed", "completed", "embedded", "chunked"].includes(value)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (["failed", "error"].includes(value)) return "border-red-200 bg-red-50 text-red-800";
  return "border-amber-200 bg-amber-50 text-amber-800";
}

function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${statusClasses(value)}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

function safeError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 404) return "Document not found or unavailable.";
    if (error.status === 403) return "This action was blocked by the security or permission policy.";
    if (error.status === 422) return "The submitted document information is invalid.";
  }
  return fallback;
}

interface DocumentsPageProps {
  initialDocumentId?: number | null;
  onExitDetails?: () => void;
}

export function DocumentsPage({ initialDocumentId = null, onExitDetails }: DocumentsPageProps) {
  const { csrfToken } = useAuth();
  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(initialDocumentId);
  const [details, setDetails] = useState<DocumentDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [files, setFiles] = useState<File[]>([]);
  const [classificationId, setClassificationId] = useState("");
  const [classifications, setClassifications] = useState<{ id: number; name: string }[]>([]);
  const [classificationError, setClassificationError] = useState<string | null>(null);
  const [teamIds, setTeamIds] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResults, setUploadResults] = useState<ProcessingRead[]>([]);
  const [mutation, setMutation] = useState<"rechunk" | "embed" | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [pendingMutation, setPendingMutation] = useState<"rechunk" | "embed" | null>(null);
  const detailsController = useRef<AbortController | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      setDocuments(await listDocuments());
    } catch (error) {
      setListError(safeError(error, "Documents could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetails = useCallback(async (documentId: number) => {
    detailsController.current?.abort();
    const controller = new AbortController();
    detailsController.current = controller;
    setDetailsLoading(true);
    setDetailsError(null);
    try {
      setDetails(await getDocumentDetails(documentId, controller.signal));
    } catch (error) {
      if (isAbortError(error)) return;
      setDetails(null);
      setDetailsError(safeError(error, "Document details could not be loaded."));
    } finally {
      if (detailsController.current === controller) {
        detailsController.current = null;
        setDetailsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    const controller = new AbortController();
    void listClassifications(controller.signal)
      .then((items) => {
        setClassifications(items);
        setClassificationError(null);
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setClassificationError(safeError(error, "Classifications could not be loaded."));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => detailsController.current?.abort(), []);

  useEffect(() => {
    if (initialDocumentId !== null) {
      setSelectedId(initialDocumentId);
      setActiveTab("overview");
      void loadDetails(initialDocumentId);
    }
  }, [initialDocumentId, loadDetails]);

  function openDocument(documentId: number) {
    setSelectedId(documentId);
    setActiveTab("overview");
    void loadDetails(documentId);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError(null);
    setUploadResults([]);
    const parsedClassification = Number(classificationId);
    if (!csrfToken) {
      setUploadError("Secure session controls are unavailable. Refresh or sign in again.");
      return;
    }
    if (!Number.isInteger(parsedClassification) || parsedClassification < 1 || files.length === 0) {
      setUploadError("Choose at least one PDF and a valid classification.");
      return;
    }
    setUploading(true);
    try {
      const options = { classificationId: parsedClassification, teamIds };
      const results =
        files.length === 1
          ? [await uploadDocument(files[0], options, csrfToken)]
          : await uploadDocuments(files, options, csrfToken);
      setUploadResults(results);
      setFiles([]);
      await loadDocuments();
    } catch (error) {
      setUploadError(safeError(error, "The upload could not be completed."));
    } finally {
      setUploading(false);
    }
  }

  async function runMutation(kind: "rechunk" | "embed") {
    if (!selectedId || !csrfToken) return;
    setMutation(kind);
    setMutationError(null);
    try {
      if (kind === "rechunk") await rechunkDocument(selectedId, csrfToken);
      else await embedDocument(selectedId, csrfToken);
      await loadDetails(selectedId);
      await loadDocuments();
    } catch (error) {
      setMutationError(safeError(error, `The ${kind} operation could not be completed.`));
    } finally {
      setMutation(null);
      setPendingMutation(null);
    }
  }

  if (selectedId !== null) {
    return (
      <div className="mx-auto max-w-7xl">
        <button type="button" onClick={() => { detailsController.current?.abort(); setDetailsLoading(false); setSelectedId(null); onExitDetails?.(); }} className="text-sm font-semibold text-sky-700 hover:text-sky-900">
          ← Back to documents
        </button>
        {detailsLoading && <p className="mt-8 text-sm text-slate-600">Loading document details…</p>}
        {detailsError && <div role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">{detailsError}</div>}
        {details && (
          <>
            <header className="mt-5 flex flex-col justify-between gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-start">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Document #{details.document.id}</p>
                <h2 className="mt-2 break-words text-2xl font-semibold tracking-tight text-slate-950">{details.document.filename}</h2>
                <p className="mt-2 text-sm text-slate-600">Uploaded {formatDate(details.document.uploaded_at)} by {details.document.uploader.name}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" disabled={!csrfToken || mutation !== null} onClick={() => setPendingMutation("rechunk")} className="rounded-lg border border-slate-300 px-3.5 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50">
                  {mutation === "rechunk" ? "Rechunking…" : "Rechunk"}
                </button>
                <button type="button" disabled={!csrfToken || mutation !== null} onClick={() => setPendingMutation("embed")} className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                  {mutation === "embed" ? "Embedding…" : "Embed / re-embed"}
                </button>
              </div>
            </header>
            {!csrfToken && <div role="alert" className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Secure session controls are unavailable. Refresh or sign in again.</div>}
            {mutationError && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{mutationError}</div>}
            <div className="mt-6 overflow-x-auto border-b border-slate-200" role="tablist" aria-label="Document details">
              <div className="flex min-w-max gap-1">
                {(["overview", "pages", "chunks", "processing"] as DetailTab[]).map((tab) => (
                  <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)} className={`border-b-2 px-4 py-3 text-sm font-semibold capitalize ${activeTab === tab ? "border-slate-900 text-slate-950" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                    {tab}
                  </button>
                ))}
              </div>
            </div>
            <section className="mt-5">
              {activeTab === "overview" && <Overview details={details} />}
              {activeTab === "pages" && <Pages details={details} />}
              {activeTab === "chunks" && <Chunks details={details} />}
              {activeTab === "processing" && <Processing details={details} />}
            </section>
            <ConfirmDialog
              open={pendingMutation !== null}
              title="Confirm document processing"
              message={pendingMutation === "rechunk" ? "Rebuild this document's chunks?" : "Generate embeddings for this document?"}
              confirmLabel={pendingMutation === "rechunk" ? "Confirm rechunk" : "Confirm embed"}
              busy={mutation !== null}
              onCancel={() => setPendingMutation(null)}
              onConfirm={() => { if (pendingMutation) void runMutation(pendingMutation); }}
            />
          </>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold text-sky-700">Authorized library</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Documents</h2>
          <p className="mt-2 text-sm text-slate-600">Only documents available to your authenticated teams are shown.</p>
        </div>
        <button type="button" onClick={() => void loadDocuments()} className="w-fit rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Refresh list</button>
      </div>

      {!csrfToken && <div role="alert" className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Secure session controls are unavailable. Refresh or sign in again.</div>}

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <h3 className="text-lg font-semibold">Upload PDF documents</h3>
        <p className="mt-1 text-sm text-slate-600">One file uses single upload; multiple files use the bulk endpoint.</p>
        <form onSubmit={handleUpload} className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_180px_minmax(0,1fr)_auto] lg:items-end">
          <label className="block text-sm font-medium text-slate-800">PDF files
            <input aria-label="PDF files" type="file" accept="application/pdf,.pdf" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" />
          </label>
          <label className="block text-sm font-medium text-slate-800">Classification
            <select aria-label="Classification" required value={classificationId} onChange={(event) => setClassificationId(event.target.value)} className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="">Select…</option>
              {classifications.map((classification) => <option key={classification.id} value={classification.id}>{classification.name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium text-slate-800">Team IDs (optional)
            <input aria-label="Team IDs" type="text" value={teamIds} onChange={(event) => setTeamIds(event.target.value)} placeholder="1, 2" className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <button type="submit" disabled={!csrfToken || uploading || classifications.length === 0} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{uploading ? "Uploading…" : "Upload selected"}</button>
        </form>
        {classificationError && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{classificationError}</div>}
        {files.length > 0 && <p className="mt-3 text-xs text-slate-500">Selected: {files.map((file) => file.name).join(", ")}</p>}
        {uploadError && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{uploadError}</div>}
        {uploadResults.length > 0 && (
          <div role="status" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            {uploadResults.map((result) => <p key={`${result.document_id}-${result.filename}`}>{result.filename}: {result.processing_status}</p>)}
          </div>
        )}
      </section>

      <section className="mt-6">
        {loading && <p className="text-sm text-slate-600">Loading authorized documents…</p>}
        {listError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">{listError}</div>}
        {!loading && !listError && documents.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center"><h3 className="font-semibold">No authorized documents</h3><p className="mt-2 text-sm text-slate-500">Upload a PDF or ask an administrator about team access.</p></div>}
        {!loading && !listError && documents.length > 0 && <DocumentTable documents={documents} onOpen={openDocument} />}
      </section>
    </div>
  );
}

function DocumentTable({ documents, onOpen }: { documents: DocumentRead[]; onOpen: (id: number) => void }) {
  return <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="overflow-x-auto"><table className="min-w-full divide-y divide-slate-200 text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-5 py-3">Document</th><th className="px-5 py-3">Classification</th><th className="px-5 py-3">Teams</th><th className="px-5 py-3">Pages</th><th className="px-5 py-3">Uploaded</th></tr></thead><tbody className="divide-y divide-slate-100">{documents.map((document) => <tr key={document.id} className="hover:bg-slate-50"><td className="px-5 py-4"><button type="button" onClick={() => onOpen(document.id)} className="max-w-sm text-left font-semibold text-sky-800 hover:underline">{document.filename}</button><p className="mt-1 text-xs text-slate-500">ID {document.id} · {formatBytes(document.file_size)} · {document.uploader.name}</p></td><td className="px-5 py-4 text-slate-700">{document.classification.name}</td><td className="px-5 py-4 text-slate-600">{document.teams.length ? document.teams.map((team) => team.name).join(", ") : "No teams"}</td><td className="px-5 py-4 text-slate-600">{document.page_count ?? "—"}</td><td className="px-5 py-4 text-slate-600">{formatDate(document.uploaded_at)}</td></tr>)}</tbody></table></div></div>;
}

function Overview({ details }: { details: DocumentDetails }) {
  const document = details.document;
  return <div className="grid gap-5 lg:grid-cols-3"><article className="rounded-xl border border-slate-200 bg-white p-5 lg:col-span-2"><h3 className="font-semibold">Metadata</h3><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-slate-500">Classification</dt><dd className="mt-1 font-medium">{document.classification.name}</dd></div><div><dt className="text-slate-500">File type</dt><dd className="mt-1 font-medium">{document.file_type}</dd></div><div><dt className="text-slate-500">Size</dt><dd className="mt-1 font-medium">{formatBytes(document.file_size)}</dd></div><div><dt className="text-slate-500">Pages</dt><dd className="mt-1 font-medium">{document.page_count ?? "Not available"}</dd></div><div><dt className="text-slate-500">Teams</dt><dd className="mt-1 font-medium">{document.teams.map((team) => team.name).join(", ") || "No teams"}</dd></div><div><dt className="text-slate-500">Tags</dt><dd className="mt-1 font-medium">{document.tags.map((tag) => tag.name).join(", ") || "No tags"}</dd></div></dl></article><article className="rounded-xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">Pipeline</h3><div className="mt-4 space-y-4 text-sm"><div className="flex items-center justify-between gap-3"><span>Processing</span><StatusBadge value={details.processing.processing_status} /></div><div className="flex items-center justify-between gap-3"><span>Chunking</span><StatusBadge value={details.chunking.chunking_status} /></div><div className="flex items-center justify-between gap-3"><span>Embedding</span><StatusBadge value={details.embedding.embedding_status} /></div></div></article></div>;
}

function Pages({ details }: { details: DocumentDetails }) {
  if (!details.pages.length) return <p className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">No extracted pages are available.</p>;
  return <div className="space-y-4">{details.pages.map((page) => <article key={page.page_number} className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Page {page.page_number}</h3><p className="text-xs text-slate-500">{page.image_count} images · OCR {page.ocr_used ? "used" : "not used"}</p></div><div className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">{page.extracted_text || "No extracted text."}</div></article>)}</div>;
}

function Chunks({ details }: { details: DocumentDetails }) {
  if (!details.chunks.length) return <p className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">No chunks are available.</p>;
  return <div className="space-y-4">{details.chunks.map((chunk) => <article key={chunk.id} className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">Chunk {chunk.chunk_index + 1} · Page {chunk.page_number}</h3><p className="text-xs text-slate-500">ID {chunk.id} · {chunk.character_count} characters · {chunk.token_count ?? "—"} tokens</p></div><div className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">{chunk.text}</div></article>)}</div>;
}

function Processing({ details }: { details: DocumentDetails }) {
  const rows = [["Processing", details.processing.processing_status], ["Started", formatDate(details.processing.processing_started_at)], ["Completed", formatDate(details.processing.processed_at)], ["Text pages", String(details.processing.text_page_count)], ["Images", String(details.processing.image_count)], ["OCR pages", String(details.processing.ocr_page_count)], ["Extracted characters", String(details.processing.extracted_text_length)], ["Chunks", String(details.chunking.chunk_count)], ["Chunking version", details.chunking.chunking_version ?? "Not available"], ["Chunked", formatDate(details.chunking.chunked_at)], ["Embeddings", String(details.embedding.embedding_count)], ["Embedding version", details.embedding.embedding_version ?? "Not available"], ["Embedded", formatDate(details.embedding.embedded_at)]];
  return <div className="rounded-xl border border-slate-200 bg-white p-5"><dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">{rows.map(([label, value]) => <div key={label}><dt className="text-slate-500">{label}</dt><dd className="mt-1 font-medium text-slate-900">{value}</dd></div>)}</dl>{(details.processing.processing_error || details.chunking.chunking_error || details.embedding.embedding_error) && <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">A pipeline operation reported an error. Retry only after reviewing the relevant status.</div>}</div>;
}

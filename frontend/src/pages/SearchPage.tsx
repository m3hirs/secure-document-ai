import { useEffect, useRef, useState, type FormEvent } from "react";

import { naturalDocumentSearch, semanticSearch } from "../api/search";
import { ApiError, isAbortError } from "../api/client";
import { EmptyState, ErrorMessage, LoadingState, StatusBadge } from "../components/ui/Feedback";
import type {
  DocumentSearchResult,
  SearchMode,
  SearchResult,
  SemanticSearchResult,
} from "../types/search";

interface SearchPageProps {
  onOpenDocument: (documentId: number) => void;
}

function isSemanticResult(result: SearchResult): result is SemanticSearchResult {
  return "chunk_text" in result;
}

function resultSnippet(result: SearchResult) {
  return isSemanticResult(result) ? result.chunk_text : result.snippet;
}

function resultPage(result: SearchResult) {
  return result.page_number;
}

function resultChunk(result: SearchResult) {
  return result.chunk_id;
}

function resultScore(result: SearchResult) {
  return result.similarity_score;
}

function safeSearchError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Search was blocked by the security or permission policy.";
    if (error.status === 422) return "The search request is invalid. Review the query and result limit.";
  }
  return "Search is temporarily unavailable. Please try again later.";
}

export function SearchPage({ onOpenDocument }: SearchPageProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("semantic");
  const [limit, setLimit] = useState(5);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [resolvedMode, setResolvedMode] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => () => requestController.current?.abort(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) {
      setError("Enter a search query.");
      return;
    }
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "semantic") {
        const response = await semanticSearch(normalized, limit, controller.signal);
        setResults(response.results);
        setResolvedMode("semantic");
        setMessage(response.message);
      } else {
        const response = await naturalDocumentSearch(normalized, limit, controller.signal);
        setResults(response.results);
        setResolvedMode(response.mode);
        setMessage(response.message);
      }
    } catch (requestError) {
      if (isAbortError(requestError)) return;
      setResults(null);
      setResolvedMode(null);
      setError(safeSearchError(requestError));
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }

  function clearSearch() {
    requestController.current?.abort();
    requestController.current = null;
    setLoading(false);
    setQuery("");
    setResults(null);
    setResolvedMode(null);
    setMessage(null);
    setError(null);
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div>
        <p className="text-sm font-semibold text-sky-700">Authorized discovery</p>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight">Search</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Search only the documents and passages available to your authenticated teams.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <label htmlFor="search-query" className="text-sm font-semibold text-slate-800">Search query</label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input id="search-query" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={4000} autoComplete="off" placeholder={mode === "semantic" ? "e.g. responsible AI monitoring" : "e.g. PDFs uploaded in the last 10 days"} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3.5 py-3 text-sm outline-none focus:border-slate-700 focus:ring-2 focus:ring-slate-200" />
          <button type="submit" className="rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white">{loading ? "Searching…" : "Search"}</button>
          <button type="button" onClick={clearSearch} disabled={loading} className="rounded-lg border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 disabled:opacity-50">Clear</button>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Search mode</legend>
            <div className="mt-2 flex gap-2">
              {(["semantic", "natural"] as SearchMode[]).map((item) => (
                <label key={item} className={`cursor-pointer rounded-lg border px-4 py-2 text-sm font-semibold capitalize ${mode === item ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700"}`}>
                  <input type="radio" name="search-mode" value={item} checked={mode === item} onChange={() => setMode(item)} className="sr-only" />
                  {item}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Result limit
            <select aria-label="Result limit" value={limit} onChange={(event) => setLimit(Number(event.target.value))} className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium normal-case tracking-normal text-slate-800 sm:max-w-40">
              {[5, 10, 20, 50].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
        <p className="mt-4 text-xs leading-5 text-slate-500">
          Natural search lets the server identify metadata, semantic, or hybrid intent. No browser-side parsing is performed.
        </p>
      </form>

      <section className="mt-6" aria-live="polite">
        {loading && <LoadingState>Searching authorized documents…</LoadingState>}
        {error && <ErrorMessage>{error}</ErrorMessage>}
        {!loading && !error && results === null && <EmptyState title="Start an authorized search" description="Results and snippets stay in this browser session only." />}
        {!loading && !error && results?.length === 0 && <EmptyState title="No accessible results found" description={message || "Try a different query or search mode."} />}
        {!loading && !error && results && results.length > 0 && (
          <div>
            <div className="mb-3 flex items-center justify-between gap-3"><p className="text-sm font-semibold text-slate-800">{results.length} result{results.length === 1 ? "" : "s"}</p>{resolvedMode && <StatusBadge>{resolvedMode} mode</StatusBadge>}</div>
            <div className="space-y-4">
              {results.map((result, index) => <ResultCard key={`${result.document_id}-${resultChunk(result) ?? "document"}-${index}`} result={result} onOpen={() => onOpenDocument(result.document_id)} />)}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ResultCard({ result, onOpen }: { result: SearchResult; onOpen: () => void }) {
  const natural = !isSemanticResult(result) ? (result as DocumentSearchResult) : null;
  const score = resultScore(result);
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Document #{result.document_id}</p><button type="button" onClick={onOpen} className="mt-1 break-words text-left text-lg font-semibold text-sky-800 hover:underline">{result.filename}</button></div>
        {score !== null && <span className="w-fit rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">Similarity {score.toFixed(3)}</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        {resultPage(result) !== null && <span>Page {resultPage(result)}</span>}
        {resultChunk(result) !== null && <span>Chunk {resultChunk(result)}</span>}
        {natural?.classification && <span>{natural.classification}</span>}
        {natural?.uploader_name && <span>Uploaded by {natural.uploader_name}</span>}
      </div>
      {resultSnippet(result) && <p className="mt-4 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-700">{resultSnippet(result)}</p>}
    </article>
  );
}

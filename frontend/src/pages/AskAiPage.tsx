import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { askDocuments } from "../api/rag";
import { ApiError, isAbortError } from "../api/client";
import { EmptyState, ErrorMessage, LoadingState, StatusBadge } from "../components/ui/Feedback";
import type { RagAnswerRead, RagSourceRead } from "../types/rag";

interface AskAiPageProps {
  onOpenDocument: (documentId: number) => void;
}

function safeRagError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 403) return "This AI request was blocked by the security or permission policy.";
    if (error.status === 422) return "The question or retrieval limit is invalid.";
    if (error.status === 503) return "Local AI service is currently unavailable.";
  }
  return "The AI request could not be completed. Please try again later.";
}

export function AskAiPage({ onOpenDocument }: AskAiPageProps) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [result, setResult] = useState<RagAnswerRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => () => requestController.current?.abort(), []);

  async function submitQuestion() {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) {
      setError("Enter a question about your accessible documents.");
      return;
    }
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await askDocuments({ question: normalizedQuestion, top_k: topK }, controller.signal));
    } catch (requestError) {
      if (isAbortError(requestError)) return;
      setError(safeRagError(requestError));
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion();
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (!loading) void submitQuestion();
    }
  }

  function clearQuestion() {
    setQuestion("");
    setResult(null);
    setError(null);
  }

  function cancelQuestion() {
    requestController.current?.abort();
    requestController.current = null;
    setLoading(false);
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <p className="text-sm font-semibold text-sky-700">Grounded document intelligence</p>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight">Ask AI</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Ask questions across documents you are authorized to access.
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Authorized documents only</span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Local AI</span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Grounded sources</span>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <label htmlFor="rag-question" className="text-sm font-semibold text-slate-800">Question</label>
        <textarea id="rag-question" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleQuestionKeyDown} maxLength={1000} rows={5} placeholder="What programming languages are listed in my resume?" className="mt-2 block w-full resize-y rounded-xl border border-slate-300 px-4 py-3 text-sm leading-6 outline-none focus:border-slate-700 focus:ring-2 focus:ring-slate-200" />
        <div className="mt-4 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <label htmlFor="rag-top-k" className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Authorized passage limit</label>
            <select id="rag-top-k" value={topK} onChange={(event) => setTopK(Number(event.target.value))} className="mt-2 block rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800">
              {[1, 3, 5, 10].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            <p className="text-xs text-slate-500">Ctrl/⌘ + Enter to submit</p>
            <div className="flex gap-2">
              {loading && <button type="button" onClick={cancelQuestion} className="rounded-lg border border-slate-400 px-4 py-2.5 text-sm font-semibold text-slate-800">Cancel</button>}
              <button type="button" disabled={loading} onClick={clearQuestion} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:opacity-50">Clear</button>
              <button type="submit" disabled={loading} className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60">{loading ? "Generating grounded answer…" : "Ask accessible documents"}</button>
            </div>
          </div>
        </div>
      </form>

      <section className="mt-6" aria-live="polite">
        {loading && <LoadingState>Retrieving authorized passages and generating a local answer…</LoadingState>}
        {error && <ErrorMessage>{error}</ErrorMessage>}
        {!loading && !error && result === null && <EmptyState title="Ask a grounded question" description="No conversation history is stored by this interface." />}
        {!loading && !error && result && <AnswerResult result={result} onOpenDocument={onOpenDocument} />}
      </section>
    </div>
  );
}

function AnswerResult({ result, onOpenDocument }: { result: RagAnswerRead; onOpenDocument: (documentId: number) => void }) {
  return (
    <div className="space-y-6">
      <article className={`rounded-2xl border bg-white p-6 shadow-sm sm:p-7 ${result.insufficient_evidence ? "border-amber-200" : "border-slate-200"}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">Answer</h3>
          <div className="flex flex-wrap gap-2"><StatusBadge>Model: {result.model}</StatusBadge><StatusBadge tone={result.insufficient_evidence ? "warning" : "success"}>{result.insufficient_evidence ? "Insufficient evidence" : "Grounded answer"}</StatusBadge></div>
        </div>
        <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-slate-800">{result.answer}</p>
      </article>

      {!result.insufficient_evidence && result.sources.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-lg font-semibold">Sources</h3><p className="text-xs text-slate-500">{result.sources.length} authorized source{result.sources.length === 1 ? "" : "s"}</p></div>
          <div className="grid gap-4 lg:grid-cols-2">{result.sources.map((source) => <SourceCard key={`${source.source_id}-${source.chunk_id}`} source={source} onOpen={() => onOpenDocument(source.document_id)} />)}</div>
        </section>
      )}
    </div>
  );
}

function SourceCard({ source, onOpen }: { source: RagSourceRead; onOpen: () => void }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs font-bold uppercase tracking-[0.14em] text-sky-700">{source.source_id}</p><button type="button" onClick={onOpen} className="mt-1 break-words text-left font-semibold text-slate-950 hover:text-sky-800 hover:underline">{source.filename}</button></div><span className="shrink-0 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800">{source.similarity.toFixed(3)}</span></div>
      <p className="mt-2 text-xs text-slate-500">Document {source.document_id} · Page {source.page_number} · Chunk {source.chunk_id}</p>
      <p className="mt-4 line-clamp-5 whitespace-pre-wrap text-sm leading-6 text-slate-700">{source.snippet}</p>
    </article>
  );
}

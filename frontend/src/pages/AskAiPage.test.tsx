import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AskAiPage } from "./AskAiPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const source = {
  source_id: "S1",
  document_id: 31,
  filename: "resume.pdf",
  page_number: 2,
  chunk_id: 71,
  snippet: "Synthetic authorized supporting passage.",
  similarity: 0.9432,
};

const groundedAnswer = {
  answer: "Python and Java are listed in the document.",
  sources: [source],
  model: "qwen2.5:1.5b",
  insufficient_evidence: false,
};

async function ask(question = "What languages are listed?") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: "Ask accessible documents" }));
  return user;
}

describe("grounded Ask AI", () => {
  it("renders the enterprise Ask AI workspace", () => {
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Ask AI" })).toBeVisible();
    expect(screen.getByText("Authorized documents only")).toBeVisible();
    expect(screen.getByText("Local AI")).toBeVisible();
    expect(screen.getByText("Grounded sources")).toBeVisible();
  });

  it("sends question and top_k without identity, renders answer and sources, and persists nothing", async () => {
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(groundedAnswer));
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Authorized passage limit"), "10");
    await user.type(screen.getByLabelText("Question"), "What languages are listed?");
    await user.click(screen.getByRole("button", { name: "Ask accessible documents" }));

    expect(await screen.findByText(groundedAnswer.answer)).toBeVisible();
    expect(screen.getByText("Model: qwen2.5:1.5b")).toBeVisible();
    expect(screen.getByText("S1")).toBeVisible();
    expect(screen.getByText("resume.pdf")).toBeVisible();
    expect(screen.getByText(source.snippet)).toBeVisible();
    expect(screen.getByText("0.943")).toBeVisible();
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(fetchMock.mock.calls[0][0]).toContain("/documents/ask");
    expect(JSON.parse(options.body as string)).toEqual({ question: "What languages are listed?", top_k: 10 });
    expect(options.body).not.toContain("user_id");
    expect(options.body).not.toContain("uploaded_by");
    expect(options.credentials).toBe("include");
    expect(storageSpy).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("navigates from a source through its document ID", async () => {
    const onOpenDocument = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(groundedAnswer));
    render(<AskAiPage onOpenDocument={onOpenDocument} />);
    const user = await ask();
    await user.click(await screen.findByRole("button", { name: "resume.pdf" }));
    expect(onOpenDocument).toHaveBeenCalledWith(31);
  });

  it("groups multiple supporting passages by source document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({
      ...groundedAnswer,
      sources: [source, { ...source, source_id: "S2", chunk_id: 72, page_number: 3 }],
    }));
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    await ask();
    expect(await screen.findByText("1 source document · 2 supporting passages")).toBeVisible();
    expect(screen.getByRole("button", { name: "resume.pdf" })).toBeVisible();
  });

  it("renders the exact insufficient-evidence response without sources", async () => {
    const answer = "I could not find enough information in the accessible documents to answer that question.";
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ answer, sources: [], model: "qwen2.5:1.5b", insufficient_evidence: true }));
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    await ask("What unsupported fact is present?");
    expect(await screen.findByText(answer)).toBeVisible();
    expect(screen.getByText("Insufficient evidence")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("shows loading state and prevents duplicate submissions", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise<Response>((resolve) => { resolveRequest = resolve; }));
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    await ask();
    expect(screen.getByRole("status")).toHaveTextContent("Retrieving authorized passages");
    expect(screen.getByRole("button", { name: "Generating grounded answer…" })).toBeDisabled();
    resolveRequest?.(jsonResponse(groundedAnswer));
    expect(await screen.findByText(groundedAnswer.answer)).toBeVisible();
  });

  it("cancels a pending local AI request without showing an error", async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, options) => {
      signal = options?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      });
    });
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    const user = await ask();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it.each([
    [403, "security or permission policy"],
    [422, "question or retrieval limit is invalid"],
    [503, "Local AI service is currently unavailable"],
    [500, "AI request could not be completed"],
  ])("handles HTTP %s with a safe message", async (status, expected) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Sensitive backend diagnostic" }, status));
    render(<AskAiPage onOpenDocument={vi.fn()} />);
    await ask();
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(screen.getByRole("alert")).not.toHaveTextContent("Sensitive backend diagnostic");
    expect(screen.getByRole("heading", { name: "Ask AI" })).toBeVisible();
  });
});

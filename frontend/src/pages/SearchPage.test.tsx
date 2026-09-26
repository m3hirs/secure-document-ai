import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SearchPage } from "./SearchPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const semanticResult = {
  document_id: 31,
  filename: "resume.pdf",
  page_number: 2,
  chunk_id: 71,
  chunk_text: "Confidential synthetic search snippet.",
  similarity_score: 0.9342,
};

const naturalResult = {
  document_id: 31,
  filename: "resume.pdf",
  classification: "Internal",
  uploaded_at: "2026-09-20T10:00:00Z",
  uploader_name: "Ava Patel",
  file_type: "application/pdf",
  page_number: 2,
  chunk_id: 71,
  snippet: "Synthetic natural-search snippet.",
  similarity_score: 0.88,
};

async function submitSearch(query: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Search query"), query);
  await user.click(screen.getByRole("button", { name: "Search" }));
  return user;
}

describe("authorized search", () => {
  it("sends a semantic request, renders authorized results and similarity, and persists nothing", async () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ results: [semanticResult], message: null }),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);

    await submitSearch("responsible AI");

    expect(await screen.findByRole("button", { name: "resume.pdf" })).toBeVisible();
    expect(screen.getByText("Similarity 0.934")).toBeVisible();
    expect(screen.getByText(semanticResult.chunk_text)).toBeVisible();
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(fetchMock.mock.calls[0][0]).toContain("/search/semantic");
    expect(JSON.parse(options.body as string)).toEqual({ query: "responsible AI", top_k: 5 });
    expect(options.body).not.toContain("user_id");
    expect(options.credentials).toBe("include");
    expect(localStorageSpy).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("uses the natural document-search contract and displays the resolved hybrid mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ mode: "hybrid", applied_filters: { file_type: "application/pdf" }, results: [naturalResult], page: 1, page_size: 10, total_returned: 1, message: null }),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText("natural"));
    await user.selectOptions(screen.getByLabelText("Result limit"), "10");
    await user.type(screen.getByLabelText("Search query"), "PDF architecture documents");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("hybrid mode")).toBeVisible();
    expect(screen.getByText(naturalResult.snippet)).toBeVisible();
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(fetchMock.mock.calls[0][0]).toContain("/search/documents");
    expect(JSON.parse(options.body as string)).toEqual({ query: "PDF architecture documents", page: 1, page_size: 10, sort: "relevance" });
    expect(options.body).not.toContain("user_id");
  });

  it("shows the no-results state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ results: [], message: "No accessible matching documents found." }),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);
    await submitSearch("missing topic");
    expect(await screen.findByText("No accessible results found")).toBeVisible();
  });

  it("shows a loading state and prevents duplicate submissions", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise<Response>((resolve) => { resolveRequest = resolve; }),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);
    await submitSearch("slow query");
    expect(screen.getByRole("status")).toHaveTextContent("Searching authorized documents");
    expect(screen.getByRole("button", { name: "Searching…" })).toBeEnabled();
    resolveRequest?.(jsonResponse({ results: [], message: null }));
    expect(await screen.findByText("No accessible results found")).toBeVisible();
  });

  it("aborts the obsolete request when a newer search is submitted", async () => {
    let firstSignal: AbortSignal | undefined;
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce((_input, options) => {
        firstSignal = options?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          firstSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
      })
      .mockResolvedValueOnce(jsonResponse({ results: [], message: null }));
    render(<SearchPage onOpenDocument={vi.fn()} />);
    const user = await submitSearch("first query");
    await user.clear(screen.getByLabelText("Search query"));
    await user.type(screen.getByLabelText("Search query"), "new query");
    await user.click(screen.getByRole("button", { name: "Searching…" }));
    expect(firstSignal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("No accessible results found")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("passes a result document ID to the authorized detail navigation", async () => {
    const onOpenDocument = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ results: [semanticResult], message: null }),
    );
    render(<SearchPage onOpenDocument={onOpenDocument} />);
    const user = await submitSearch("resume skills");
    await user.click(await screen.findByRole("button", { name: "resume.pdf" }));
    expect(onOpenDocument).toHaveBeenCalledWith(31);
  });

  it("shows a permission error for 403 without replacing the search UI", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Forbidden" }, 403),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);
    await submitSearch("restricted query");
    expect(await screen.findByRole("alert")).toHaveTextContent("security or permission policy");
    expect(screen.getByRole("heading", { name: "Search" })).toBeVisible();
  });

  it("shows safe validation feedback for 422", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Parser-specific confidential detail" }, 422),
    );
    render(<SearchPage onOpenDocument={vi.fn()} />);
    await submitSearch("invalid natural query");
    expect(await screen.findByRole("alert")).toHaveTextContent("search request is invalid");
    expect(screen.getByRole("alert")).not.toHaveTextContent("Parser-specific");
  });
});

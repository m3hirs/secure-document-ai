import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthContext, type AuthContextValue } from "../contexts/AuthContext";
import { DocumentsPage } from "./DocumentsPage";

const document = {
  id: 11,
  filename: "architecture.pdf",
  file_type: "application/pdf",
  file_size: 2048,
  page_count: 2,
  uploaded_at: "2026-09-25T10:00:00Z",
  created_at: "2026-09-25T10:00:00Z",
  classification: { id: 3, name: "Engineering" },
  uploader: { id: 7, name: "Ava Patel" },
  tags: [{ id: 5, name: "Architecture" }],
  teams: [{ id: 2, name: "Software" }],
  is_archived: false,
};

const processing = {
  document_id: 11,
  filename: "architecture.pdf",
  processing_status: "processed",
  page_count: 2,
  extracted_text_length: 240,
  text_page_count: 2,
  image_count: 0,
  ocr_page_count: 0,
  processing_started_at: "2026-09-25T10:00:00Z",
  processed_at: "2026-09-25T10:01:00Z",
  processing_error: null,
};

const pages = [{ page_number: 1, extracted_text: "Synthetic page content", has_text: true, image_count: 0, ocr_used: false }];
const chunks = [{ id: 91, document_id: 11, page_id: 81, page_number: 1, chunk_index: 0, text: "Synthetic chunk content", character_count: 23, token_count: 3, source_start_char: 0, source_end_char: 23, chunk_metadata: null, created_at: "2026-09-25T10:01:00Z" }];
const chunking = { document_id: 11, filename: "architecture.pdf", chunking_status: "chunked", chunk_count: 1, chunking_version: "v1", chunked_at: "2026-09-25T10:01:00Z", chunking_error: null };
const embedding = { document_id: 11, filename: "architecture.pdf", embedding_status: "embedded", embedding_count: 1, embedding_version: "e5-small-v1", embedded_at: "2026-09-25T10:02:00Z", embedding_error: null };

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function requestPath(input: RequestInfo | URL) {
  return new URL(String(input)).pathname;
}

function detailResponse(path: string) {
  if (path === "/documents/11") return jsonResponse(document);
  if (path.endsWith("/processing")) return jsonResponse(processing);
  if (path.endsWith("/pages")) return jsonResponse(pages);
  if (path.endsWith("/chunks")) return jsonResponse(chunks);
  if (path.endsWith("/chunking")) return jsonResponse(chunking);
  if (path.endsWith("/embedding")) return jsonResponse(embedding);
  return null;
}

function renderDocuments(
  csrfToken: string | null = "csrf-in-memory",
  props: { initialDocumentId?: number | null; onExitDetails?: () => void; onArchiveComplete?: () => void } = {},
) {
  const value: AuthContextValue = {
    user: { id: 7, name: "Ava Patel", email: "ava@example.com", is_active: true },
    csrfToken,
    loading: false,
    authenticated: true,
    canLogout: csrfToken !== null,
    securityError: null,
    login: vi.fn(),
    logout: vi.fn(),
  };
  return render(<AuthContext.Provider value={value}><DocumentsPage {...props} /></AuthContext.Provider>);
}

describe("document management", () => {
  it("renders the authorized document list", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([document]));
    renderDocuments();
    expect(await screen.findByRole("button", { name: "architecture.pdf" })).toBeVisible();
    expect(screen.getByText("Engineering")).toBeVisible();
    expect(screen.getByText("Software")).toBeVisible();
  });

  it("renders an empty authorized-library state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderDocuments();
    expect(await screen.findByText("No authorized documents")).toBeVisible();
  });

  it("loads document metadata, pages, chunks, and pipeline details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents") return jsonResponse([document]);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "architecture.pdf" }));
    expect(await screen.findByText("Document #11")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /pages/i }));
    expect(screen.getByText("Synthetic page content")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /chunks/i }));
    expect(screen.getByText("Synthetic chunk content")).toBeVisible();
  });

  it("uses generic unavailable wording for a document 404", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (requestPath(input) === "/documents") return jsonResponse([document]);
      return jsonResponse({ detail: "Document not found" }, 404);
    });
    renderDocuments();
    await userEvent.setup().click(await screen.findByRole("button", { name: "architecture.pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Document not found or unavailable.");
  });

  it("aborts grouped detail requests when leaving the document route", async () => {
    const detailSignals: AbortSignal[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
      const path = requestPath(input);
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      if (path === "/teams") return jsonResponse([{ id: 2, name: "Software" }]);
      const signal = options?.signal;
      if (signal) detailSignals.push(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      });
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "architecture.pdf" }));
    await user.click(screen.getByRole("button", { name: /Back to documents/i }));
    expect(detailSignals).toHaveLength(6);
    expect(detailSignals.every((signal) => signal.aborted)).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uploads multipart data without client identity fields", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
      const path = requestPath(input);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      if (path === "/teams") return jsonResponse([{ id: 2, name: "Software" }, { id: 4, name: "Machine Learning" }]);
      if (path === "/documents/upload") return jsonResponse({ ...processing, filename: "safe.pdf" }, 201);
      if (path === "/documents") return jsonResponse([]);
      return jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    const file = new File(["%PDF-safe-test"], "safe.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("PDF files"), file);
    await user.selectOptions(await screen.findByLabelText("Classification"), "3");
    await user.selectOptions(await screen.findByLabelText("Teams"), "2");
    await user.click(screen.getByRole("button", { name: "Upload selected" }));
    expect(await screen.findByRole("status")).toHaveTextContent("safe.pdf: processed");

    const uploadCall = fetchMock.mock.calls.find(([input]) => requestPath(input) === "/documents/upload");
    const options = uploadCall?.[1] as RequestInit;
    const form = options.body as FormData;
    expect(form.get("classification_id")).toBe("3");
    expect(form.get("team_ids")).toBe("2");
    expect(form.has("user_id")).toBe(false);
    expect(form.has("uploaded_by")).toBe(false);
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf-in-memory");
  });

  it("requires a named team selection before upload", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      if (path === "/teams") return jsonResponse([{ id: 2, name: "Software" }]);
      if (path === "/documents") return jsonResponse([]);
      return jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("PDF files"), new File(["%PDF"], "safe.pdf", { type: "application/pdf" }));
    await user.selectOptions(await screen.findByLabelText("Classification"), "3");
    await user.click(screen.getByRole("button", { name: "Upload selected" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least one team");
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/documents/upload")).toBe(false);
  });

  it("disables document mutations when CSRF capability is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents") return jsonResponse([document]);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments(null);
    expect(await screen.findByText("Secure session controls are unavailable. Refresh or sign in again.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Upload selected" })).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "architecture.pdf" }));
    expect(await screen.findByRole("button", { name: "Rechunk" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Embed / re-embed" })).toBeDisabled();
  });

  it.each([
    ["Rechunk", "/documents/11/rechunk", chunking],
    ["Embed / re-embed", "/documents/11/embed", embedding],
  ])("runs %s with CSRF and refreshes document data", async (buttonName, mutationPath, result) => {
    const paths: string[] = [];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      paths.push(path);
      if (path === "/documents") return jsonResponse([document]);
      if (path === mutationPath) return jsonResponse(result);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "architecture.pdf" }));
    await screen.findByText("Document #11");
    const detailCallsBefore = paths.filter((path) => path === "/documents/11").length;
    await user.click(screen.getByRole("button", { name: buttonName }));
    await user.click(screen.getByRole("button", { name: buttonName === "Rechunk" ? "Confirm rechunk" : "Confirm embed" }));
    await waitFor(() => expect(paths.filter((path) => path === "/documents/11").length).toBeGreaterThan(detailCallsBefore));
    const mutationCall = fetchMock.mock.calls.find(([input]) => requestPath(input) === mutationPath);
    const options = mutationCall?.[1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf-in-memory");
  });

  it("keeps the document UI present after a mutation 403", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/documents/11/rechunk") return jsonResponse({ detail: "Forbidden" }, 403);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "architecture.pdf" }));
    await user.click(await screen.findByRole("button", { name: "Rechunk" }));
    await user.click(screen.getByRole("button", { name: "Confirm rechunk" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("security or permission policy");
    expect(screen.getByText("Document #11")).toBeVisible();
  });

  it("removes an authorized document from only the current workspace after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents/11/archive") return jsonResponse({ ...document, is_archived: true });
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments("csrf-in-memory", { initialDocumentId: 11 });
    const user = userEvent.setup();
    await screen.findByText("Document #11");
    await user.click(screen.getByRole("button", { name: "Remove from my workspace" }));
    expect(screen.getByText("Remove this document from your workspace? This will not delete the document for other authorized users.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Document removed from your workspace.");
    expect(screen.queryByRole("button", { name: "architecture.pdf" })).not.toBeInTheDocument();

    const archiveCall = fetchMock.mock.calls.find(([input]) => requestPath(input) === "/documents/11/archive");
    const options = archiveCall?.[1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf-in-memory");
    expect(JSON.parse(String(options.body))).toEqual({});
    expect(String(options.body)).not.toContain("user_id");
  });

  it("shows the current user's archived documents and restores one with CSRF", async () => {
    const archivedDocument = { ...document, is_archived: true };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      if (url.pathname === "/documents/11/restore") return jsonResponse(document);
      if (url.pathname === "/documents" && url.searchParams.get("include_archived") === "true") return jsonResponse([archivedDocument]);
      if (url.pathname === "/documents") return jsonResponse([document]);
      if (url.pathname === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      return jsonResponse({}, 500);
    });
    renderDocuments();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByRole("button", { name: "Restore" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Document restored to your workspace.");
    expect(screen.queryByRole("button", { name: "architecture.pdf" })).not.toBeInTheDocument();
    const restoreCall = fetchMock.mock.calls.find(([input]) => requestPath(input) === "/documents/11/restore");
    expect(new Headers(restoreCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-in-memory");
  });

  it("preserves authenticated document UI when archive is rejected with 403", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents/11/archive") return jsonResponse({ detail: "Forbidden" }, 403);
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments("csrf-in-memory", { initialDocumentId: 11 });
    const user = userEvent.setup();
    await screen.findByText("Document #11");
    await user.click(screen.getByRole("button", { name: "Remove from my workspace" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("security or permission policy");
    expect(screen.getByText("Document #11")).toBeVisible();
  });

  it("uses generic unavailable wording when archive returns 404", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === "/documents/11/archive") return jsonResponse({ detail: "Document not found" }, 404);
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/classifications") return jsonResponse([{ id: 3, name: "Engineering" }]);
      return detailResponse(path) ?? jsonResponse({}, 500);
    });
    renderDocuments("csrf-in-memory", { initialDocumentId: 11 });
    const user = userEvent.setup();
    await screen.findByText("Document #11");
    await user.click(screen.getByRole("button", { name: "Remove from my workspace" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Document not found or unavailable.");
  });
});

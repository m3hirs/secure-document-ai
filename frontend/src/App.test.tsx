import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";

const authenticatedUser = {
  id: 7,
  name: "Ava Patel",
  email: "ava@example.com",
  is_active: true,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApplication(initialEntry = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("authentication UI", () => {
  it("shows login for an unauthenticated protected deep link", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    renderApplication("/documents/31");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  it("renders login and hides the protected shell after a 401", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Authentication required" }, 401),
    );

    renderApplication();

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: /Welcome, Ava/ })).not.toBeInTheDocument();
  });

  it("logs in, keeps auth material in memory, and sends no user_id", async () => {
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ user: authenticatedUser, csrf_token: "csrf-memory-only" }),
      );

    renderApplication();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ava@example.com");
    await user.type(screen.getByLabelText("Password"), "not-persisted");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));

    expect(await screen.findByRole("heading", { name: "Welcome, Ava Patel" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).not.toBeInTheDocument();
    expect(storageSpy).not.toHaveBeenCalled();

    const loginOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(loginOptions.credentials).toBe("include");
    expect(JSON.parse(loginOptions.body as string)).toEqual({
      email: "ava@example.com",
      password: "not-persisted",
    });
    expect(loginOptions.body).not.toContain("user_id");
  });

  it("logs out with CSRF and clears the protected shell", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ user: authenticatedUser, csrf_token: "csrf-memory-only" }),
      )
      .mockResolvedValueOnce(jsonResponse({ message: "Logged out" }));

    renderApplication();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ava@example.com");
    await user.type(screen.getByLabelText("Password"), "not-persisted");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));
    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
    const logoutOptions = fetchMock.mock.calls[2][1] as RequestInit;
    expect(new Headers(logoutOptions.headers).get("X-CSRF-Token")).toBe("csrf-memory-only");
    expect(logoutOptions.credentials).toBe("include");
  });

  it("restores the user and rotates an in-memory CSRF token after refresh", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "rotated-memory-only" }));
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");

    renderApplication();

    expect(await screen.findByRole("heading", { name: "Welcome, Ava Patel" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
    expect(storageSpy).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[0][0]).toContain("/auth/me");
    expect(fetchMock.mock.calls[1][0]).toContain("/auth/csrf");
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ credentials: "include", method: "POST" }),
    );
  });

  it("treats a CSRF restoration 401 as unauthenticated", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401));

    renderApplication();

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Welcome, Ava Patel" })).not.toBeInTheDocument();
  });

  it("keeps the restored user but disables mutations when CSRF restoration is forbidden", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse({ detail: "Request origin is not allowed" }, 403));

    renderApplication();

    expect(await screen.findByRole("heading", { name: "Welcome, Ava Patel" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Session security restoration was blocked",
    );
  });

  it("preserves authenticated state and in-memory CSRF when logout is forbidden", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ user: authenticatedUser, csrf_token: "csrf-memory-only" }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: "CSRF validation failed" }, 403));

    renderApplication();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ava@example.com");
    await user.type(screen.getByLabelText("Password"), "not-persisted");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));
    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your current session remains active",
    );
    expect(screen.getByRole("heading", { name: "Welcome, Ava Patel" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
    const logoutOptions = fetchMock.mock.calls[2][1] as RequestInit;
    expect(new Headers(logoutOptions.headers).get("X-CSRF-Token")).toBe("csrf-memory-only");
  });

  it("returns to login when a later request receives 401", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ user: authenticatedUser, csrf_token: "csrf-memory-only" }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401));

    renderApplication();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ava@example.com");
    await user.type(screen.getByLabelText("Password"), "not-persisted");
    await user.click(screen.getByRole("button", { name: "Sign in securely" }));
    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("returns to login when the document list receives 401", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authenticatedUser))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "rotated-memory-only" }))
      .mockResolvedValueOnce(jsonResponse({ detail: "Authentication required" }, 401));

    renderApplication();
    await screen.findByRole("heading", { name: "Welcome, Ava Patel" });
    await userEvent.setup().click(screen.getAllByRole("link", { name: "Documents" })[0]);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Documents" })).not.toBeInTheDocument();
  });

  it("returns to login when search receives 401", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = new URL(String(input)).pathname;
      if (path === "/auth/me") return jsonResponse(authenticatedUser);
      if (path === "/auth/csrf") return jsonResponse({ csrf_token: "rotated-memory-only" });
      return jsonResponse({ detail: "Authentication required" }, 401);
    });

    renderApplication();
    await screen.findByRole("heading", { name: "Welcome, Ava Patel" });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("link", { name: "Search" })[0]);
    await user.type(screen.getByLabelText("Search query"), "resume");
    await user.click(screen.getAllByRole("button", { name: "Search" }).at(-1)!);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  it("opens the existing authorized document details from a search result", async () => {
    const document = { id: 31, filename: "resume.pdf", file_type: "application/pdf", file_size: 1024, page_count: 1, uploaded_at: "2026-09-20T10:00:00Z", created_at: "2026-09-20T10:00:00Z", classification: { id: 1, name: "Internal" }, uploader: { id: 7, name: "Ava Patel" }, tags: [], teams: [{ id: 2, name: "Software" }] };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = new URL(String(input)).pathname;
      if (path === "/auth/me") return jsonResponse(authenticatedUser);
      if (path === "/auth/csrf") return jsonResponse({ csrf_token: "rotated-memory-only" });
      if (path === "/search/semantic") return jsonResponse({ results: [{ document_id: 31, filename: "resume.pdf", page_number: 1, chunk_id: 9, chunk_text: "Synthetic result", similarity_score: 0.9 }], message: null });
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/documents/31") return jsonResponse(document);
      if (path.endsWith("/processing")) return jsonResponse({ document_id: 31, filename: "resume.pdf", processing_status: "processed", page_count: 1, extracted_text_length: 10, text_page_count: 1, image_count: 0, ocr_page_count: 0, processing_started_at: null, processed_at: null, processing_error: null });
      if (path.endsWith("/pages")) return jsonResponse([]);
      if (path.endsWith("/chunks")) return jsonResponse([]);
      if (path.endsWith("/chunking")) return jsonResponse({ document_id: 31, filename: "resume.pdf", chunking_status: "chunked", chunk_count: 0, chunking_version: "v1", chunked_at: null, chunking_error: null });
      if (path.endsWith("/embedding")) return jsonResponse({ document_id: 31, filename: "resume.pdf", embedding_status: "embedded", embedding_count: 0, embedding_version: "e5-small-v1", embedded_at: null, embedding_error: null });
      return jsonResponse({}, 500);
    });

    renderApplication();
    await screen.findByRole("heading", { name: "Welcome, Ava Patel" });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("link", { name: "Search" })[0]);
    await user.type(screen.getByLabelText("Search query"), "resume");
    await user.click(screen.getAllByRole("button", { name: "Search" }).at(-1)!);
    await user.click(await screen.findByRole("button", { name: "resume.pdf" }));

    expect(await screen.findByText("Document #31")).toBeVisible();
    expect(screen.getByRole("heading", { name: "resume.pdf" })).toBeVisible();
  });

  it("returns to login when Ask AI receives 401", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = new URL(String(input)).pathname;
      if (path === "/auth/me") return jsonResponse(authenticatedUser);
      if (path === "/auth/csrf") return jsonResponse({ csrf_token: "rotated-memory-only" });
      return jsonResponse({ detail: "Authentication required" }, 401);
    });
    renderApplication();
    await screen.findByRole("heading", { name: "Welcome, Ava Patel" });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("link", { name: "Ask AI" })[0]);
    await user.type(screen.getByLabelText("Question"), "What is supported?");
    await user.click(screen.getByRole("button", { name: "Ask accessible documents" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  it("opens authorized document details from an Ask AI source", async () => {
    const document = { id: 31, filename: "resume.pdf", file_type: "application/pdf", file_size: 1024, page_count: 1, uploaded_at: "2026-09-20T10:00:00Z", created_at: "2026-09-20T10:00:00Z", classification: { id: 1, name: "Internal" }, uploader: { id: 7, name: "Ava Patel" }, tags: [], teams: [{ id: 2, name: "Software" }] };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = new URL(String(input)).pathname;
      if (path === "/auth/me") return jsonResponse(authenticatedUser);
      if (path === "/auth/csrf") return jsonResponse({ csrf_token: "rotated-memory-only" });
      if (path === "/documents/ask") return jsonResponse({ answer: "Python is listed.", sources: [{ source_id: "S1", document_id: 31, filename: "resume.pdf", page_number: 1, chunk_id: 9, snippet: "Synthetic source", similarity: 0.9 }], model: "qwen2.5:1.5b", insufficient_evidence: false });
      if (path === "/documents") return jsonResponse([document]);
      if (path === "/documents/31") return jsonResponse(document);
      if (path.endsWith("/processing")) return jsonResponse({ document_id: 31, filename: "resume.pdf", processing_status: "processed", page_count: 1, extracted_text_length: 10, text_page_count: 1, image_count: 0, ocr_page_count: 0, processing_started_at: null, processed_at: null, processing_error: null });
      if (path.endsWith("/pages")) return jsonResponse([]);
      if (path.endsWith("/chunks")) return jsonResponse([]);
      if (path.endsWith("/chunking")) return jsonResponse({ document_id: 31, filename: "resume.pdf", chunking_status: "chunked", chunk_count: 0, chunking_version: "v1", chunked_at: null, chunking_error: null });
      if (path.endsWith("/embedding")) return jsonResponse({ document_id: 31, filename: "resume.pdf", embedding_status: "embedded", embedding_count: 0, embedding_version: "e5-small-v1", embedded_at: null, embedding_error: null });
      return jsonResponse({}, 500);
    });
    renderApplication();
    await screen.findByRole("heading", { name: "Welcome, Ava Patel" });
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("link", { name: "Ask AI" })[0]);
    await user.type(screen.getByLabelText("Question"), "What language is listed?");
    await user.click(screen.getByRole("button", { name: "Ask accessible documents" }));
    await user.click(await screen.findByRole("button", { name: "resume.pdf" }));
    expect(await screen.findByText("Document #31")).toBeVisible();
  });

  it("restores the session before loading an authenticated document deep link", async () => {
    const document = { id: 31, filename: "resume.pdf", file_type: "application/pdf", file_size: 1024, page_count: 1, uploaded_at: "2026-09-20T10:00:00Z", created_at: "2026-09-20T10:00:00Z", classification: { id: 1, name: "Internal" }, uploader: { id: 7, name: "Ava Patel" }, tags: [], teams: [] };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = new URL(String(input)).pathname;
      if (path === "/auth/me") return jsonResponse(authenticatedUser);
      if (path === "/auth/csrf") return jsonResponse({ csrf_token: "rotated-memory-only" });
      if (path === "/classifications") return jsonResponse([{ id: 1, name: "Internal" }]);
      if (path === "/documents/31") return jsonResponse(document);
      if (path.endsWith("/processing")) return jsonResponse({ document_id: 31, filename: "resume.pdf", processing_status: "processed", page_count: 1, extracted_text_length: 10, text_page_count: 1, image_count: 0, ocr_page_count: 0, processing_started_at: null, processed_at: null, processing_error: null });
      if (path.endsWith("/pages")) return jsonResponse([]);
      if (path.endsWith("/chunks")) return jsonResponse([]);
      if (path.endsWith("/chunking")) return jsonResponse({ document_id: 31, filename: "resume.pdf", chunking_status: "chunked", chunk_count: 0, chunking_version: "v1", chunked_at: null, chunking_error: null });
      if (path.endsWith("/embedding")) return jsonResponse({ document_id: 31, filename: "resume.pdf", embedding_status: "embedded", embedding_count: 0, embedding_version: "e5-small-v1", embedded_at: null, embedding_error: null });
      return jsonResponse({}, 500);
    });
    renderApplication("/documents/31");
    expect(await screen.findByText("Document #31")).toBeVisible();
    expect(screen.getByRole("heading", { name: "resume.pdf" })).toBeVisible();
  });
});

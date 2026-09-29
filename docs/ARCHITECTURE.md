# Architecture

## System boundary

```text
React browser application
        |
        | HTTPS + HttpOnly session cookie + CSRF header for mutations
        v
FastAPI routing and validated session principal
        |
        v
SQL authorization predicates
        |
        +--> document ingestion / page extraction / OCR / chunking
        +--> metadata and pgvector semantic search
        +--> authorized RAG context selection and deterministic grounding
        |
        v
PostgreSQL + pgvector               Local Ollama
                                              ^
                         authorized context only |
```

Authentication establishes who the requester is. Authorization determines
which documents that identity may access. Retrieval selects evidence from that
authorized set. Generation produces text only after authorized evidence has
been selected. These are separate layers and must not be collapsed.

## Identity and session flow

1. The browser submits email and password to `/auth/login` over HTTPS.
2. FastAPI verifies the Argon2id password hash for an active existing user.
3. A cryptographically random opaque session and CSRF token are generated.
   Only their hashes are stored in `user_sessions`.
4. The raw session token is returned only as an HttpOnly cookie. The CSRF token
   is held in React memory, never localStorage or sessionStorage.
5. Each protected request resolves a server-side `Principal` from the session.
   Client-supplied user IDs are not accepted as identity.
6. After browser refresh, `/auth/me` restores identity and `/auth/csrf` rotates
   the session-bound CSRF token.

## Authorization and team model

Users and teams have a many-to-many relationship. Documents and teams also
have a many-to-many relationship. A document is accessible only when the
authenticated user's teams intersect the document's allowed teams. The shared
SQL predicate is applied before document rows, chunks, titles, snippets, or
metadata are returned. Unauthorized and nonexistent document IDs receive the
same generic 404 behavior.

Frontend visibility is convenience only. Hiding a link or record in React is
not authorization; the database query remains the final access-control
boundary.

## Upload and processing flow

1. Authenticated browser submits one or more PDFs with a server-provided
   classification and optional team IDs.
2. Origin and CSRF checks protect the persistent mutation. Uploader identity
   comes from the authenticated principal.
3. Files are validated and stored under generated local names.
4. PyMuPDF extracts page text and image counts. Image-only pages can use local
   Tesseract OCR.
5. Page records, processing status, and history events are stored.
6. Normalized page text is chunked and can be embedded locally with
   multilingual E5 into pgvector.

## Search flow

Metadata search uses deterministic parsed filters. General content search runs
two independent PostgreSQL-authorized retrieval arms: normalized lexical
filename/chunk matching and multilingual E5 pgvector similarity. Both apply
team authorization and the current user's archive exclusion before returning
text. Results are deduplicated and fused with weighted reciprocal rank fusion;
exact lexical evidence is preferred without comparing lexical and cosine raw
scores directly. Strong semantic-only evidence remains available for genuine
topic and multilingual queries, while weak semantic-only neighbors fail closed.

Named-document requests are parsed deterministically into a target and an
action/topic. The target is resolved only within the active authorized
workspace using exact filename, normalized filename/basename, safe aliases,
and finally conservative fuzzy matching. Zero matches fail closed and multiple
plausible matches require clarification; vector similarity never proves that a
named document exists.

## RAG flow

1. The authenticated principal's user ID is passed internally to authorized
   hybrid retrieval.
2. Bounded context selection preserves authorized source metadata and stays
   below a conservative context budget.
3. The selected passages are explicitly marked as untrusted reference data.
4. Local Ollama produces JSON constrained to dynamically authorized source IDs.
5. Python validates source IDs and deterministic categorized evidence. Invalid
   or unsupported output fails closed to the exact insufficient-evidence
   response with no sources.
6. Public sources are built from Python-owned authorized records, never from
   untrusted model-generated metadata.

## Local-only AI boundary

PDF extraction, OCR, embeddings, retrieval, summarization, and generation are
local. Ollama is addressed through loopback. The application contains no cloud
LLM or hosted OCR path. Network egress controls remain a deployment defense in
depth.

## Fail-closed behavior

Inactive, expired, idle, revoked, or malformed sessions are rejected. Missing
CSRF capability disables persistent frontend mutations. Unauthorized document
IDs are generic 404s. Empty or invalid RAG evidence returns insufficient
evidence rather than guessed content. Local model failures become sanitized
service-unavailable responses.

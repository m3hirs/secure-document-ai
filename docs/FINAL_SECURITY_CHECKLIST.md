# Final security acceptance checklist

Use approved non-confidential test data. Record reviewer, revision, environment,
and date with the release evidence.

## Authentication

- [ ] No public registration or default administrator exists.
- [ ] Valid login works; invalid, inactive, and unprovisioned users fail uniformly.
- [ ] Password hashes are Argon2id and absent from API responses/logs.
- [ ] Logout revokes the session; post-logout `/auth/me` returns 401.

## Authorization

- [ ] Identity comes only from the server-validated session.
- [ ] Ava Patel's Software/Machine-Learning membership cannot access Design-only document 35.
- [ ] Document 35 direct document, pages, chunks, and processing routes return generic 404.
- [ ] Document 35 rechunk and embed mutations return generic 404.
- [ ] Document 35 is absent from metadata, semantic, natural, and hybrid search.
- [ ] Document 35 cannot be summarized and never appears in RAG sources.

## CSRF and CORS

- [ ] Persistent mutations require exact allowed Origin and current CSRF token.
- [ ] Refresh rotates/restores CSRF capability without browser persistence.
- [ ] Old/wrong CSRF tokens fail and do not clear valid client state deceptively.
- [ ] CORS allows only reviewed exact origins with credentials; wildcard is absent.

## Cookies and browser storage

- [ ] Production cookie is Secure, HttpOnly, `__Host-`, `Path=/`, with no Domain.
- [ ] SameSite behavior matches reviewed frontend/API topology.
- [ ] No session or CSRF token exists in localStorage/sessionStorage.
- [ ] Questions, answers, snippets, and confidential state are not persisted.

## CSP and headers

- [ ] API emits nosniff, no-referrer, Permissions-Policy, and frame denial.
- [ ] Production API and frontend host emit reviewed CSP without unsafe directives.
- [ ] HSTS is enabled only after successful HTTPS validation.

## Documents and storage

- [ ] Uploaded PDFs are validated and stored outside source control under generated names.
- [ ] Uploader identity is server-derived; browser does not send `uploaded_by`/`user_id`.
- [ ] Storage ACLs, encryption, retention, backup, and deletion policy are reviewed.
- [ ] OCR gracefully handles unavailable Tesseract without external services.

## Search and RAG

- [ ] Authorization is included in SQL before chunks or metadata are returned.
- [ ] Retrieved PDF content is treated as untrusted reference material.
- [ ] Dynamic source-ID validation rejects unauthorized or invented IDs.
- [ ] Deterministic grounding rejects unsupported/mislabeled category items.
- [ ] Unsupported questions fail closed with no sources.
- [ ] Ollama calls only the loopback endpoint and no cloud AI service is configured.

## Database, backup, and migration

- [ ] PostgreSQL uses a least-privileged service account and restricted network path.
- [ ] pgvector extension and expected Alembic head are present.
- [ ] A recent backup is verified through a restore drill.
- [ ] Migration and application rollback procedures are approved.

## Frontend

- [ ] Protected deep links restore session before data loads.
- [ ] Unauthenticated routes show login without protected content.
- [ ] Cancellation, error boundary, keyboard navigation, focus, and mobile navigation work.
- [ ] Production `VITE_API_BASE_URL` is explicit HTTPS and SPA fallback is configured.

## Logging and deployment

- [ ] Logs contain no passwords, tokens, cookies, prompts, document text, embeddings, or answers.
- [ ] TLS, trusted proxies, rate limits, request sizes, timeouts, monitoring, and alerting are configured.
- [ ] Dependency/vulnerability and license reviews are recorded.
- [ ] Backend/frontend tests and production build pass from the release revision.

# Deployment runbook

This is an operator checklist, not an automated deployment. Replace bracketed
values with reviewed environment-specific values; do not invent domains.

## Pre-deployment

1. Freeze the reviewed application revision and dependency lockfiles.
2. Create a verified PostgreSQL backup and record restore instructions.
3. Confirm Alembic state without changing it:
   `python -m alembic current` and `python -m alembic heads`.
4. Configure secrets outside source control using `docs/ENVIRONMENT.md`.
5. Provision PostgreSQL with pgvector, Python, Tesseract if OCR is required,
   Ollama, `qwen2.5:1.5b`, and the offline E5 model cache.
6. Verify the service account can read the model cache and read/write only the
   intended document storage directory.
7. Run backend tests, frontend tests/build, dependency/security scans, and the
   final security checklist in an approved staging environment.

## Backend deployment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --requirement requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Provision passwords only for existing approved users:

```powershell
.\.venv\Scripts\python.exe scripts\set_user_password.py --email user@example.test
```

Run FastAPI under a supervised ASGI process manager appropriate to the host.
Use a non-root service identity, bounded workers, graceful shutdown, protected
environment injection, and health monitoring. Do not use `--reload` in
production.

## Frontend deployment

```powershell
cd frontend
$env:VITE_API_BASE_URL = "https://[reviewed-api-host]"
pnpm.cmd install --frozen-lockfile
pnpm.cmd run test
pnpm.cmd run build
```

Serve `frontend/dist` as immutable static assets. Rewrite `/dashboard`,
`/documents/*`, `/search`, and `/ask` to `index.html` for SPA deep links. Do not
cache `index.html` indefinitely.

## Reverse proxy and TLS

- Terminate HTTPS with a valid certificate and forward only trusted headers.
- Configure exact reviewed frontend/API hostnames in CORS and Origin settings.
- Use a Secure `__Host-` cookie with `Path=/` and no Domain.
- Apply the reviewed CSP to frontend HTML and retain backend security headers.
- Enable HSTS only after HTTPS behavior and all subdomains are confirmed.
- Bound upload/request sizes, header sizes, upstream timeouts, and connections.
- Apply shared login rate limiting at the gateway or shared backend store.
- Restrict database, Ollama, model-cache, and document-storage network/filesystem access.

## Post-deployment validation

1. Confirm `/health` without exposing internals.
2. Log in with the approved test user and verify `/auth/me` and CSRF rotation.
3. Verify authorized document list and detail endpoints.
4. Verify document 35 is absent and direct access is generic 404.
5. Run an authorized search and confirm restricted metadata is absent.
6. Ask a supported and unsupported RAG question; validate authorized sources.
7. Log out, confirm revocation, and confirm `/auth/me` returns 401.
8. Inspect cookies, CSP/security headers, browser storage, and sanitized logs.

## Rollback

1. Stop traffic to the failed revision and preserve relevant sanitized logs and
   deployment evidence.
2. Restore the previous tested application and frontend artifacts.
3. Do not casually run `alembic downgrade`, especially after passwords or
   sessions have been provisioned. Determine whether the schema is backward
   compatible with the previous application.
4. If a database restore is required, stop writes, retain the failed database
   for investigation, restore the verified backup, and validate consistency.
5. Re-run authentication, authorization, document-35, search, RAG, and logout
   checks before reopening traffic.

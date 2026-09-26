# Secure Document AI

Secure Document AI is a local-first enterprise document platform for secure PDF
ingestion, team-authorized discovery, summarization, and grounded question
answering. It combines a FastAPI/PostgreSQL backend with a React frontend while
keeping OCR, embeddings, and language-model inference on local infrastructure.

## Key features

- Secure single and bulk PDF upload with local UUID-based storage
- PyMuPDF text extraction and local Tesseract OCR for image-only pages
- Page-aware normalization, chunking, and processing history
- Local multilingual E5 embeddings stored in PostgreSQL pgvector
- Deterministic metadata, semantic, and hybrid search
- Local Ollama summaries and authorization-aware RAG with verified sources
- Stage 8 deterministic grounding for technology-category questions
- React document, search, and Ask AI workspaces with protected deep links
- Request cancellation, safe error boundaries, responsive navigation, and
  accessible controls

## Security model

- Argon2id password hashes and no public registration
- Opaque server-side sessions in HttpOnly cookies; raw tokens are not stored
- Refresh-safe, session-bound CSRF rotation for persistent mutations
- Exact Origin validation and credentialed CORS allowlists
- SQL-level team authorization before document metadata or chunks are returned
- Generic 404 responses for unauthorized and nonexistent document IDs
- Local-only OCR, embeddings, and Ollama inference
- Dynamically authorized RAG source IDs and fail-closed evidence validation
- Production cookie/config validation and restrictive browser security headers

Frontend visibility is not an authorization boundary. PostgreSQL authorization
predicates remain the final document access-control boundary.

See [SECURITY.md](docs/SECURITY.md) and
[FINAL_SECURITY_CHECKLIST.md](docs/FINAL_SECURITY_CHECKLIST.md).

## Architecture

```text
React -> FastAPI -> session authentication -> SQL team authorization
      -> document/search/RAG services -> PostgreSQL + pgvector
                                     -> local Ollama
```

The detailed identity, upload, search, RAG, and CSRF flows are in
[ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

- Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic
- PostgreSQL, psycopg2, pgvector
- PyMuPDF, Pillow, pytesseract/Tesseract
- sentence-transformers with multilingual E5
- Local Ollama using `qwen2.5:1.5b`
- React, TypeScript, React Router, Vite, Tailwind CSS
- pytest, Vitest, and Testing Library

The tested dependency inventory is in [DEPENDENCIES.md](docs/DEPENDENCIES.md).

## Local prerequisites

- Python 3.11 or newer
- PostgreSQL with pgvector (the current Windows installation may use port 1710)
- Node.js and pnpm
- Ollama with `qwen2.5:1.5b` already installed
- Local multilingual E5 model cache
- Tesseract when OCR is required

## Backend setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with the local PostgreSQL connection and reviewed settings. Never
commit it. All supported variables are documented in
[ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Database migration

Create the target database through the approved PostgreSQL administration
process, then apply migrations without recreating existing data:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Alembic is the authentication-schema source of truth. Transitional startup
initialization remains for legacy non-authentication tables and should be
removed in a separately reviewed migration-only cleanup.

## Password provisioning

Provision only an existing approved user. The password is entered through a
hidden interactive prompt and active sessions for that user are revoked:

```powershell
.\.venv\Scripts\python.exe scripts\set_user_password.py --email user@example.test
```

The tool can alternatively use `--user-id`. It never creates an account, role,
or administrator.

## Ollama setup

Ollama must listen locally on `127.0.0.1:11434` and have
`qwen2.5:1.5b` available. Model installation is an operator step:

```powershell
ollama pull qwen2.5:1.5b
```

Do not download models automatically during application startup.

## Frontend setup

```powershell
cd frontend
pnpm.cmd install --frozen-lockfile
Copy-Item .env.example .env
pnpm.cmd run dev
```

Development uses `http://localhost:8000` unless overridden. Production requires
an explicit HTTPS `VITE_API_BASE_URL`; Vite variables are public and must never
contain secrets.

## Running locally

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host localhost --port 8000
```

Frontend:

```powershell
cd frontend
pnpm.cmd run dev
```

Open `http://localhost:5173`. Local Swagger is available at
`http://localhost:8000/docs`.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-final
cd frontend
pnpm.cmd run test
pnpm.cmd run build
```

Use a new writable `--basetemp` name if Windows has retained handles from an
earlier pytest run.

## Project structure

```text
app/                 FastAPI routes, security, models, schemas, services
alembic/             reviewed database migrations
frontend/            React/TypeScript application
scripts/             provisioning, backfill, and privacy-safe diagnostics
tests/               backend security and feature regression tests
docs/                architecture, security, environment, demo, deployment
data/documents/      runtime uploads; excluded from source control
```

Stage 8 diagnostic scripts are retained intentionally for local privacy-safe RAG
evaluation. They are not application routes and must not run automatically in
production.

## Demo

Follow [DEMO.md](docs/DEMO.md) for the 5–8 minute company presentation and
[STAGE9_E2E_SECURITY_CHECKLIST.md](docs/STAGE9_E2E_SECURITY_CHECKLIST.md) for
the manual browser smoke test.

## Deployment

Use [DEPLOYMENT.md](docs/DEPLOYMENT.md). Production requires HTTPS, exact
origins, a Secure `__Host-` cookie, SPA history fallback, CSP on the frontend
host, storage/database protection, shared login rate limiting, backups, and
monitoring. Deployment is intentionally not automated by this repository.

## Security notes

- Never commit `.env`, uploaded PDFs, database dumps, model caches, keys, build
  output, or test temporary directories.
- Never log passwords, cookies, tokens, prompts, document text, embeddings, or
  generated answers.
- Do not expose PostgreSQL or Ollama directly to untrusted networks.
- HSTS should be enabled only after TLS and hostname behavior are confirmed.

## Known limitations

- Ollama and the configured local model must be available.
- RAG responses are non-streaming.
- Secure persistent conversation history is not implemented.
- MFA and SSO/OIDC are not implemented.
- Login rate limiting requires a gateway or shared store.
- Production hosting, TLS, HSTS, monitoring, and backups are operator work.
- FastAPI lifecycle and TestClient dependency deprecation warnings remain.
- Classification administration is read-only; classifications are not managed
  in the frontend.
- There is no admin role or authorization bypass.

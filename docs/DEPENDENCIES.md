# Dependency record

This document records the dependency state exercised by the Stage 10 test run.
`requirements.txt` defines supported Python ranges; `pnpm-lock.yaml` is the
authoritative exact frontend dependency graph. Do not upgrade dependencies as
part of a deployment without a separate review and regression run.

## Backend runtime

| Dependency | Tested version | Purpose |
|---|---:|---|
| FastAPI | 0.141.1 | HTTP API, dependency injection, OpenAPI |
| Starlette | 1.6.0 | ASGI primitives and middleware |
| Uvicorn | 0.53.0 | Local/deployment ASGI server |
| SQLAlchemy | 2.0.54 | ORM and SQL authorization queries |
| Alembic | 1.20.0 | Reviewed database migrations |
| psycopg2-binary | 2.9.13 | PostgreSQL driver |
| pgvector | 0.5.0 | Vector column and similarity integration |
| Pydantic | 2.13.5 | Request, response, and settings validation |
| pydantic-settings | 2.15.0 | Environment-backed configuration |
| tzdata | 2026.4 | IANA timezone data, including Windows deployments |
| pwdlib | 0.3.1 | Password hashing interface |
| argon2-cffi | 25.1.0 | Argon2id implementation |
| PyMuPDF | 1.28.2 | Local PDF parsing and rendering |
| pytesseract | 0.3.13 | Local OCR adapter |
| Pillow | 11.3.0 | OCR image handling |
| python-multipart | 0.0.32 | Multipart PDF uploads |
| sentence-transformers | 6.1.0 | Local multilingual E5 embeddings |
| transformers | 5.17.0 | Embedding-model runtime |
| torch | 2.14.0 | Local tensor/model runtime |

PostgreSQL with the `vector` extension, Tesseract, and Ollama are external
runtime dependencies and are not installed by `pip`.

## Backend test tooling

The tested environment used pytest 8.4.2 and HTTPX 0.28.1. Tests currently
emit upstream TestClient/lifecycle deprecation warnings; see Known Limitations.

## Frontend

| Dependency | Locked version | Purpose |
|---|---:|---|
| React / React DOM | 19.3.0 | UI runtime |
| React Router DOM | 7.18.4 | Protected routing and deep links |
| Vite | 8.3.1 | Development and production builds |
| TypeScript | 7.0.2 | Static type checking |
| Tailwind CSS | 4.3.3 | Design system utilities |
| Vitest | 5.0.1 | Frontend test runner |
| Testing Library React | 16.3.3 | User-focused component tests |
| jsdom | 30.1.1 | Browser-like test environment |

Use `pnpm install --frozen-lockfile` for reproducible frontend installation.

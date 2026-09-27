# Environment reference

Environment variables are case-insensitive through Pydantic settings. Examples
below are placeholders only. Never commit real credentials.

| Variable | Purpose | Required | Safe development example | Production notes |
|---|---|---|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection | Yes | `postgresql+psycopg2://app:change-me@localhost:1710/secure_document_ai` | Use a secret manager and least-privileged DB user |
| `APP_ENVIRONMENT` | Enables production validation/CSP | Optional | `development` | Set exactly `production` |
| `DOCUMENT_STORAGE_DIR` | Local PDF storage root | Optional | `data/documents` | Use protected persistent storage and backups |
| `CHUNK_MAX_CHARACTERS` | Chunk character target | Optional | `1500` | Must be positive |
| `CHUNK_OVERLAP_CHARACTERS` | Adjacent chunk overlap | Optional | `200` | Nonnegative and below max |
| `CHUNKING_VERSION` | Chunking algorithm marker | Optional | `v1` | Change only with reviewed reprocessing plan |
| `EMBEDDING_MODEL_NAME` | Local E5 model identifier | Optional | `intfloat/multilingual-e5-small` | Model must be pre-provisioned locally |
| `EMBEDDING_MODEL_CACHE_DIR` | Offline model cache | Optional | `E:\AI-Models` | Protect directory and prevent accidental commits |
| `EMBEDDING_DIMENSION` | pgvector/model dimension | Optional | `384` | Current implementation requires 384 |
| `EMBEDDING_BATCH_SIZE` | Local encoding batch size | Optional | `16` | Tune only after resource testing |
| `EMBEDDING_VERSION` | Stored embedding version | Optional | `e5-small-v1` | Coordinate changes with re-embedding |
| `SEMANTIC_SEARCH_TOP_K` | Default semantic result count | Optional | `10` | Must not exceed maximum |
| `SEMANTIC_SEARCH_MAX_TOP_K` | Maximum semantic result count | Optional | `50` | Positive integer |
| `SEMANTIC_SEARCH_MIN_SIMILARITY` | Minimum cosine similarity retained by semantic/hybrid retrieval | Optional | `0.81` | Range 0–1; higher is stricter. API score is `1 - pgvector cosine distance` for normalized E5 vectors |
| `APP_TIMEZONE` | Natural-search relative-date zone | Optional | `Asia/Kolkata` | Use an installed IANA zone; keep `tzdata` available on Windows |
| `SESSION_COOKIE_NAME` | Opaque session cookie name | Optional | `secure_document_session` | Production requires a `__Host-` name |
| `SESSION_COOKIE_SECURE` | Restrict cookie to HTTPS | Optional | `false` | Must be `true` in production |
| `SESSION_COOKIE_SAMESITE` | Cookie SameSite policy | Optional | `lax` | `none` requires Secure; review cross-site need |
| `SESSION_COOKIE_PATH` | Cookie scope | Optional | `/` | Production requires `/` |
| `SESSION_ABSOLUTE_TIMEOUT_MINUTES` | Hard session lifetime | Optional | `480` | Positive, maximum 43,200 |
| `SESSION_IDLE_TIMEOUT_MINUTES` | Idle session lifetime | Optional | `30` | Positive, max 1,440 and not above absolute |
| `SESSION_TOKEN_BYTES` | Random token entropy input | Optional | `32` | Minimum 32 |
| `FRONTEND_ALLOWED_ORIGINS` | Exact credentialed browser origins | Optional in development | `["http://localhost:5173"]` | Required HTTPS origins; no wildcard/path/query |
| `TESSERACT_CMD` | Local Tesseract executable | Optional | `D:\Tesseract\tesseract.exe` | OCR gracefully disables when unavailable |

`SEMANTIC_SEARCH_MIN_SIMILARITY=0.81` was selected from the bundled local
synthetic calibration set: minimum positive `0.844183`, median positive
`0.904725`, maximum negative `0.779004`, and median negative `0.765088`.
It is not a probability or universal relevance boundary. Retrieval also uses
a conservative lexical-support gate for unscoped Latin-script queries. Re-run
`scripts/calibrate_semantic_relevance.py` and validate with approved internal
queries before changing the value for a deployment corpus.

The Ollama URL (`127.0.0.1:11434`), model (`qwen2.5:1.5b`), context budget,
and deterministic generation settings are currently local application
constants, not environment variables.

## Frontend

| Variable | Purpose | Required | Development | Production |
|---|---|---|---|---|
| `VITE_API_BASE_URL` | Public API origin used by browser requests | Optional only in development | `http://localhost:8000` | Explicit HTTPS origin required; missing/HTTP values show a safe configuration error |

All Vite variables are public browser configuration. Never put passwords,
database URLs, cookies, private keys, or other secrets in frontend environment
files.

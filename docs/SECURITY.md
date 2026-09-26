# Security model

## Authentication

- Existing users receive passwords through the interactive provisioning tool;
  there is no public registration or default administrator.
- Passwords are hashed with Argon2id through `pwdlib`. Password hashes are not
  included in API schemas or logs.
- Sessions use random opaque tokens. PostgreSQL stores SHA-256 token hashes,
  CSRF hashes, expiry/idle timestamps, and revocation state—not raw secrets.
- The browser receives the session only in an HttpOnly cookie. Production
  requires a Secure `__Host-` cookie with `Path=/` and no Domain attribute.
- SameSite is configurable; `SameSite=None` is rejected unless Secure is true.
- Logout revokes the server-side session. Password changes revoke existing
  active sessions.

## CSRF, Origin, and CORS

Persistent cookie-authenticated mutations require both an exact allowed Origin
and the current session-bound `X-CSRF-Token`. Refresh-safe CSRF recovery rotates
the token after `/auth/me`. CORS uses exact configured origins and credentials;
wildcards are rejected. CSRF tokens remain only in React memory.

## Authorization

The client never supplies identity. FastAPI obtains `principal.user_id` from a
validated session and passes it to services. Document, page, chunk, processing,
search, summary, and RAG queries apply team authorization in SQL. Unauthorized
IDs use generic 404 behavior to avoid confirming confidential object existence.

**Frontend hiding UI is not an authorization boundary. The database query
remains the final access-control boundary.**

## RAG and local inference

Authorized chunks are filtered in PostgreSQL before they reach context
selection or Ollama. Selected PDF content is untrusted reference data, not an
instruction channel. Source IDs use a dynamic authorized enum. Python verifies
returned IDs and Stage 8 deterministic category/evidence rules; unsupported
output fails closed. Source metadata is always taken from Python-owned records.
Ollama and multilingual E5 run locally.

## Browser and response controls

- No authentication token or confidential AI state is stored in localStorage
  or sessionStorage.
- Questions, snippets, answers, and tokens are not placed in URLs.
- Responses set nosniff, no-referrer, restrictive Permissions-Policy, and frame
  denial. Production adds a CSP without `unsafe-inline` or `unsafe-eval`.
- The frontend static host must also set its reviewed CSP. HSTS should be
  enabled only after production HTTPS is verified.

## Logging and files

Application code must not log passwords, raw session/CSRF tokens, prompts,
document text, embeddings, or model answers. Uploaded documents, database
dumps, environment files, private keys, model caches, build output, and test
temporary directories are excluded by repository ignore rules.

## Remaining deployment responsibilities

- TLS termination, HSTS activation, trusted proxy configuration, request/body
  limits, shared login rate limiting, and network egress restrictions.
- Secrets management, database backup/restore drills, encrypted disks, storage
  ACLs, log retention/redaction, vulnerability scanning, and monitoring.
- SSO/OIDC and MFA are not implemented. There is no admin bypass.

# Company demo runbook

Target duration: 5–8 minutes. Use approved synthetic/demo documents only.

1. **Login** — Sign in as Ava Patel. Mention Argon2id passwords, an opaque
   HttpOnly session, and in-memory CSRF protection. Do not show credentials.
2. **Dashboard** — Point out local-only AI and authenticated workspace status.
3. **Documents** — Show the authorized library and explain that team access is
   enforced in SQL, not by hidden frontend controls.
4. **Document detail** — Open the approved resume document. Briefly show
   metadata, extracted pages, chunks, processing, and embeddings.
5. **Upload** — Show the server-provided classification dropdown. If time
   permits, upload only an approved disposable demo PDF.
6. **Search** — Run a semantic or natural search and open one authorized result.
7. **Grounded Ask AI** — Ask: “What programming languages are listed in my
   resume?” Show the concise answer, authorized source card, and source link.
8. **Category grounding** — Ask one approved infrastructure or API technology
   question. Explain deterministic evidence pruning and fail-closed behavior.
9. **Insufficient evidence** — Ask an unsupported question and show the safe
   insufficient-evidence response rather than a guess.
10. **Restricted document** — Explain that Design-only document 35 is absent;
    directly visiting `/documents/35` shows only generic unavailable wording.
11. **Logout** — Sign out and refresh. Confirm protected routes return to login.

Do not display developer tools containing tokens, confidential text, raw model
prompts, database connection strings, or real production data during the demo.

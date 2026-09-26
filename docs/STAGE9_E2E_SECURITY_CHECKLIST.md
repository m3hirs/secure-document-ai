# Stage 9 end-to-end security smoke test

Use an approved local/demo dataset only. Do not automate this checklist against
real confidential data. Test user: **Ava Patel**.

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

## Authentication

- [ ] Sign in as Ava Patel and confirm the protected dashboard appears.
- [ ] Refresh a protected route; user and CSRF capability restore before the protected operation is enabled.
- [ ] Sign out; refresh and confirm login is shown.
- [ ] A protected deep link while signed out shows login and no protected data.

## Documents

- [ ] Only Ava's authorized documents are visible.
- [ ] Document 35 is absent from the list.
- [ ] `/documents/35` displays only generic unavailable wording.
- [ ] Upload a safe test PDF using the classification dropdown.
- [ ] The browser request does not send `uploaded_by` or `user_id`.

## Search

- [ ] Semantic and natural search return allowed results.
- [ ] Document 35 is absent from titles, snippets, and metadata.
- [ ] Submitting a newer search cancels the obsolete request without an application error.

## Ask AI

- [ ] An authorized question returns an answer and source cards.
- [ ] Every source opens an authorized document.
- [ ] Document 35 is absent from sources and answer metadata.
- [ ] An unsupported question returns the insufficient-evidence state.
- [ ] Cancel a pending request; no error or automatic retry occurs.

## Browser security inspection

- [ ] Session cookie is HttpOnly and unavailable to JavaScript.
- [ ] No CSRF token exists in localStorage or sessionStorage.
- [ ] No question, answer, snippet, prompt, or CSRF value appears in URLs.
- [ ] Confidential snippets and answers are not persisted in browser storage.
- [ ] Protected backend requests without a session return 401 without revealing whether a document exists.
- [ ] Production responses have the reviewed CSP, frame protection, nosniff, Referrer-Policy, and Permissions-Policy headers.

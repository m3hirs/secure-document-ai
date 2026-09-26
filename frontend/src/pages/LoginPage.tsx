import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { BrandMark } from "../components/ui/BrandMark";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      setPassword("");
    } catch (requestError) {
      setPassword("");
      if (requestError instanceof ApiError && requestError.status === 401) {
        setError("The email or password is incorrect.");
      } else if (requestError instanceof ApiError && requestError.status === 403) {
        setError("Sign-in was blocked by the application security policy.");
      } else {
        setError("Unable to sign in right now. Please try again later.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-slate-100 lg:grid-cols-[minmax(0,1.05fr)_minmax(440px,0.95fr)]">
      <section className="relative hidden overflow-hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(148,163,184,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.12)_1px,transparent_1px)] [background-size:44px_44px]" />
        <div className="relative flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl bg-white text-slate-950">
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M7 3.75h7l3 3v13.5H7z" />
              <path d="M14 3.75v3h3M9.5 11h5M9.5 14h5M9.5 17h3" />
            </svg>
          </div>
          <span className="font-semibold">Secure Document AI</span>
        </div>
        <div className="relative max-w-xl pb-12">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-sky-300">Private by design</p>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight xl:text-5xl">
            Your company knowledge, secured at every layer.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">
            Access authorized documents, local intelligence, and grounded answers from one protected workspace.
          </p>
        </div>
        <p className="relative text-xs text-slate-500">Local processing · Team authorization · Auditable access</p>
      </section>

      <section className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-9 flex items-center gap-3 lg:hidden">
            <BrandMark />
            <span className="font-semibold">Secure Document AI</span>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/60 sm:p-9">
            <p className="text-sm font-semibold text-sky-700">Secure access</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Welcome back</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Sign in with your provisioned company account.</p>

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-800">Email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  autoFocus
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-slate-700 focus:ring-2 focus:ring-slate-200"
                  placeholder="name@company.com"
                />
              </div>
              <div>
                <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-800">Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-slate-700 focus:ring-2 focus:ring-slate-200"
                  placeholder="Enter your password"
                />
              </div>
              {error && (
                <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
                  {error}
                </div>
              )}
              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Signing in…" : "Sign in securely"}
              </button>
            </form>
          </div>
          <p className="mt-5 text-center text-xs leading-5 text-slate-500">
            Your session is stored in a protected HttpOnly cookie. This application never stores your password or session token.
          </p>
        </div>
      </section>
    </main>
  );
}

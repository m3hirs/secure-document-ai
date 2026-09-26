import { useAuth } from "../hooks/useAuth";

export function DashboardPage() {
  const { user, canLogout } = useAuth();

  return (
    <div className="mx-auto max-w-6xl">
      <section className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm sm:p-9">
        <div className="flex flex-col justify-between gap-7 sm:flex-row sm:items-start">
          <div>
            <p className="text-sm font-semibold text-sky-700">Authenticated workspace</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Welcome, {user?.name}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Your identity is established by a server-side session. Document visibility and permissions remain enforced by the backend.
            </p>
          </div>
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800">
            <span className="size-2 rounded-full bg-emerald-500" />
            Session authenticated
          </div>
        </div>
      </section>
      <section className="mt-6 grid gap-5 md:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Account</p>
          <dl className="mt-5 space-y-4 text-sm">
            <div>
              <dt className="text-slate-500">Name</dt>
              <dd className="mt-1 font-medium text-slate-900">{user?.name}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Email</dt>
              <dd className="mt-1 font-medium text-slate-900">{user?.email}</dd>
            </div>
          </dl>
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">Security status</p>
          <div className="mt-5 flex items-start gap-3">
            <div className="mt-0.5 grid size-8 place-items-center rounded-full bg-slate-100 text-slate-700">
              <span aria-hidden="true">✓</span>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">Session cookie protected</p>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                {canLogout
                  ? "CSRF protection is active for this login session."
                  : "Secure session controls are unavailable. Refresh or sign in again before making changes."}
              </p>
            </div>
          </div>
        </article>
      </section>
    </div>
  );
}

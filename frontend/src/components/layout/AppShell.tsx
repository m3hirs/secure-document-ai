import { useState, type PropsWithChildren } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { BrandMark } from "../ui/BrandMark";

const navigation = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/documents", label: "Documents" },
  { to: "/search", label: "Search" },
  { to: "/ask", label: "Ask AI" },
];

export function AppShell({ children }: PropsWithChildren) {
  const { user, logout, canLogout, securityError } = useAuth();
  const location = useLocation();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLogoutError(null);
    setLoggingOut(true);
    try {
      await logout();
    } catch {
      setLogoutError(
        "Sign-out was blocked or unavailable. Your current session remains active.",
      );
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white lg:flex lg:flex-col">
        <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-6">
          <BrandMark />
          <div>
            <p className="font-semibold tracking-tight">Secure Document AI</p>
            <p className="text-xs text-slate-500">Private enterprise workspace</p>
          </div>
        </div>
        <nav aria-label="Primary" className="flex-1 space-y-1 px-4 py-6">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${isActive || (item.to === "/documents" && location.pathname.startsWith("/documents/")) ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`}>
              <span className="size-1.5 rounded-full bg-current" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-4">
          <p className="truncate text-sm font-medium text-slate-800">{user?.name}</p>
          <p className="truncate text-xs text-slate-500">{user?.email}</p>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex min-h-20 items-center justify-between border-b border-slate-200 bg-white/95 px-5 backdrop-blur sm:px-8">
          <div className="flex items-center gap-3 lg:hidden">
            <BrandMark />
            <span className="font-semibold">Secure Document AI</span>
          </div>
          <div className="hidden lg:block">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Workspace</p>
            <h1 className="text-lg font-semibold">{location.pathname.startsWith("/documents") ? "Documents" : navigation.find((item) => item.to === location.pathname)?.label || "Dashboard"}</h1>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut || !canLogout}
            title={!canLogout ? "Session security must be restored before secure logout." : undefined}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loggingOut ? "Signing out…" : "Sign out"}
          </button>
        </header>
        <nav aria-label="Mobile primary" className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `whitespace-nowrap rounded-lg px-3 py-2 text-sm font-semibold ${isActive || (item.to === "/documents" && location.pathname.startsWith("/documents/")) ? "bg-slate-900 text-white" : "text-slate-600"}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        {logoutError && (
          <div role="alert" className="mx-5 mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 sm:mx-8">
            {logoutError}
          </div>
        )}
        {securityError && (
          <div role="alert" className="mx-5 mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 sm:mx-8">
            {securityError}
          </div>
        )}
        <main className="px-5 py-8 sm:px-8 lg:py-10">{children}</main>
      </div>
    </div>
  );
}

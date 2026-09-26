import type { ReactNode } from "react";

export function LoadingState({ children }: { children: ReactNode }) {
  return <div role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">{children}</div>;
}

export function ErrorMessage({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">{children}</div>;
}

export function EmptyState({ title, description }: { title: string; description: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center"><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm text-slate-500">{description}</p></div>;
}

export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "warning" | "danger" }) {
  const styles = {
    neutral: "border-slate-200 bg-slate-50 text-slate-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
    danger: "border-red-200 bg-red-50 text-red-800",
  }[tone];
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${styles}`}>{children}</span>;
}

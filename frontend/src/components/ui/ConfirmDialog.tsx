import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({ open, title, message, confirmLabel, busy = false, onCancel, onConfirm }: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);
  if (!open) return null;
  return <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4" role="presentation" onKeyDown={(event) => { if (event.key === "Escape" && !busy) onCancel(); }}><section role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"><h2 id="confirm-dialog-title" className="text-lg font-semibold text-slate-950">{title}</h2><p className="mt-3 text-sm leading-6 text-slate-600">{message}</p><div className="mt-6 flex justify-end gap-3"><button ref={cancelRef} type="button" disabled={busy} onClick={onCancel} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">Cancel</button><button type="button" disabled={busy} onClick={onConfirm} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{confirmLabel}</button></div></section></div>;
}

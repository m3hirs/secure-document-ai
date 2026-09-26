export function LoadingScreen() {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-50" aria-busy="true">
      <div className="flex items-center gap-3 text-sm font-medium text-slate-600">
        <span className="size-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-800" />
        Verifying your secure session…
      </div>
    </main>
  );
}

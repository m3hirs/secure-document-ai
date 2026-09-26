import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from "react";

interface ErrorBoundaryState { failed: boolean }

export class ErrorBoundary extends Component<PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState { return { failed: true }; }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Confidential component state and raw error objects are intentionally not logged.
  }

  private retry = () => {
    this.setState({ failed: false });
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return <main className="grid min-h-screen place-items-center bg-slate-100 px-5"><section className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm"><h1 className="text-2xl font-semibold text-slate-950">Something went wrong while loading Secure Document AI.</h1><p className="mt-3 text-sm leading-6 text-slate-600">No application details were displayed. Reload to start a clean session view.</p><button type="button" onClick={this.retry} className="mt-6 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white">Reload application</button></section></main>;
  }
}

export function ConfigurationError({ message }: { message: string }) {
  return <main className="grid min-h-screen place-items-center bg-slate-100 px-5"><section role="alert" className="w-full max-w-lg rounded-2xl border border-red-200 bg-white p-8 text-center shadow-sm"><h1 className="text-2xl font-semibold text-slate-950">Secure Document AI is not configured.</h1><p className="mt-3 text-sm text-slate-600">{message}</p></section></main>;
}

import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { LoadingScreen } from "./components/ui/LoadingScreen";
import { useAuth } from "./hooks/useAuth";
import { AskAiPage } from "./pages/AskAiPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { SearchPage } from "./pages/SearchPage";

export default function App() {
  const { loading, authenticated } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!authenticated) return <LoginPage />;

  return <ErrorBoundary><AppShell><Routes>
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="/dashboard" element={<DashboardPage />} />
    <Route path="/documents" element={<DocumentsRoute />} />
    <Route path="/documents/:documentId" element={<DocumentRoute />} />
    <Route path="/search" element={<SearchRoute />} />
    <Route path="/ask" element={<AskRoute />} />
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></AppShell></ErrorBoundary>;
}

function DocumentsRoute() {
  const location = useLocation();
  const notice = typeof location.state === "object" && location.state !== null && "notice" in location.state && typeof location.state.notice === "string" ? location.state.notice : null;
  return <DocumentsPage initialSuccessMessage={notice} />;
}

function DocumentRoute() {
  const navigate = useNavigate();
  const parsedId = Number(useParams().documentId);
  if (!Number.isInteger(parsedId) || parsedId < 1) {
    return <div role="alert" className="mx-auto max-w-4xl rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">Document not found or unavailable.</div>;
  }
  return <DocumentsPage
    initialDocumentId={parsedId}
    onExitDetails={() => navigate("/documents")}
    onArchiveComplete={() => navigate("/documents", { state: { notice: "Document removed from your workspace." } })}
  />;
}

function SearchRoute() {
  const navigate = useNavigate();
  return <SearchPage onOpenDocument={(documentId) => navigate(`/documents/${documentId}`)} />;
}

function AskRoute() {
  const navigate = useNavigate();
  return <AskAiPage onOpenDocument={(documentId) => navigate(`/documents/${documentId}`)} />;
}

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { ConfigurationError, ErrorBoundary } from "./components/ui/ErrorBoundary";
import { frontendConfig } from "./config";
import { AuthProvider } from "./contexts/AuthContext";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {frontendConfig.error ? (
      <ConfigurationError message={frontendConfig.error} />
    ) : (
      <BrowserRouter>
        <AuthProvider>
          <ErrorBoundary><App /></ErrorBoundary>
        </AuthProvider>
      </BrowserRouter>
    )}
  </StrictMode>,
);

export interface FrontendConfig {
  apiBaseUrl: string;
  error: string | null;
}

export function resolveFrontendConfig(
  configuredValue: string | undefined,
  production: boolean,
): FrontendConfig {
  const configured = configuredValue?.trim();
  if (production && !configured) {
    return { apiBaseUrl: "", error: "VITE_API_BASE_URL must be configured for production." };
  }
  const candidate = configured || "http://localhost:8000";
  try {
    const parsed = new URL(candidate);
    const rootPath = parsed.pathname === "/" || parsed.pathname === "";
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.host || parsed.username || parsed.password || !rootPath || parsed.search || parsed.hash) {
      throw new Error("invalid API origin");
    }
    if (production && parsed.protocol !== "https:") {
      return { apiBaseUrl: "", error: "VITE_API_BASE_URL must use HTTPS in production." };
    }
    return { apiBaseUrl: candidate.replace(/\/$/, ""), error: null };
  } catch {
    return { apiBaseUrl: "", error: "VITE_API_BASE_URL must be an absolute HTTP(S) origin." };
  }
}

export const frontendConfig = resolveFrontendConfig(
  import.meta.env.VITE_API_BASE_URL,
  import.meta.env.PROD,
);

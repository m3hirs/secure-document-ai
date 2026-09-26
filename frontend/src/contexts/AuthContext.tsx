import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  rotateCsrfToken,
} from "../api/auth";
import { ApiError, setUnauthorizedHandler } from "../api/client";
import type { AuthUser, LoginCredentials } from "../types/auth";

export interface AuthContextValue {
  user: AuthUser | null;
  csrfToken: string | null;
  loading: boolean;
  authenticated: boolean;
  canLogout: boolean;
  securityError: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [securityError, setSecurityError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearAuthentication = useCallback(() => {
    setUser(null);
    setCsrfToken(null);
    setSecurityError(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(clearAuthentication);
    return () => setUnauthorizedHandler(null);
  }, [clearAuthentication]);

  useEffect(() => {
    let active = true;

    async function restoreSession() {
      try {
        const restoredUser = await getCurrentUser();
        if (!active) return;
        setUser(restoredUser);
        setCsrfToken(null);
        setSecurityError(null);

        try {
          const restoredSecurity = await rotateCsrfToken();
          if (active) setCsrfToken(restoredSecurity.csrf_token);
        } catch (error) {
          if (!active) return;
          setCsrfToken(null);
          if (error instanceof ApiError && error.status === 401) {
            clearAuthentication();
          } else {
            setSecurityError(
              error instanceof ApiError && error.status === 403
                ? "Session security restoration was blocked by the application origin policy. State-changing actions are disabled."
                : "Session security could not be restored. State-changing actions are disabled.",
            );
          }
        }
      } catch (error) {
        if (active) {
          clearAuthentication();
          if (!(error instanceof ApiError) || error.status !== 401) {
            console.warn("Authentication check was unavailable.");
          }
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void restoreSession();
    return () => {
      active = false;
    };
  }, [clearAuthentication]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const result = await loginRequest(credentials);
    setUser(result.user);
    setCsrfToken(result.csrf_token);
    setSecurityError(null);
  }, []);

  const logout = useCallback(async () => {
    if (!csrfToken) {
      throw new Error("Secure logout requires a CSRF token from the current login.");
    }
    await logoutRequest(csrfToken);
    clearAuthentication();
  }, [clearAuthentication, csrfToken]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      csrfToken,
      loading,
      authenticated: user !== null,
      canLogout: user !== null && csrfToken !== null,
      securityError,
      login,
      logout,
    }),
    [csrfToken, loading, login, logout, securityError, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}


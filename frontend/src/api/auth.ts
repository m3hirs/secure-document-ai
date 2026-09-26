import type {
  AuthUser,
  CsrfTokenResponse,
  LoginCredentials,
  LoginResponse,
  LogoutResponse,
} from "../types/auth";
import { apiRequest } from "./client";

export function getCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>("/auth/me");
}

export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: credentials.email,
      password: credentials.password,
    }),
  });
}

export function logout(csrfToken: string): Promise<LogoutResponse> {
  return apiRequest<LogoutResponse>("/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function rotateCsrfToken(): Promise<CsrfTokenResponse> {
  return apiRequest<CsrfTokenResponse>("/auth/csrf", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

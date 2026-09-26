import { frontendConfig } from "../config";

export const API_BASE_URL = frontendConfig.apiBaseUrl;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

function responseDetail(payload: unknown, fallback: string): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (frontendConfig.error) {
    throw new ApiError(0, "Frontend configuration is invalid.");
  }
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  let payload: unknown = null;
  if (response.status !== 204) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      payload = await response.json();
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      unauthorizedHandler?.();
    }
    throw new ApiError(
      response.status,
      responseDetail(payload, `Request failed with status ${response.status}`),
    );
  }

  return payload as T;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

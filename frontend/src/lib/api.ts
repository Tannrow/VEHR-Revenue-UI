import { getBrowserAccessToken } from "@/lib/auth";

export class ApiError extends Error {
  status: number;
  info?: unknown;

  constructor(status: number, message: string, info?: unknown) {
    super(message);
    this.status = status;
    this.info = info;
  }
}

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const CUTOVER_FRONTEND_HOSTS = new Set(["360-encompass.com", "www.360-encompass.com"]);
const CUTOVER_API_BASE_URL = "https://api.360-encompass.com";

function getApiBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured) {
    return configured;
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    if (CUTOVER_FRONTEND_HOSTS.has(host)) {
      return CUTOVER_API_BASE_URL;
    }
  }
  return DEFAULT_API_BASE_URL;
}

function buildUrl(path: string) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const baseUrl = getApiBaseUrl().replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl}${normalizedPath}`;
}

function getErrorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim().length > 0) {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => String(item)).join("; ");
    }
    if (detail && typeof detail === "object") {
      if ("message" in detail && typeof (detail as { message?: unknown }).message === "string") {
        return (detail as { message: string }).message;
      }
      if ("errors" in detail && Array.isArray((detail as { errors?: unknown }).errors)) {
        return (detail as { errors: unknown[] }).errors.map((item) => String(item)).join("; ");
      }
      return JSON.stringify(detail);
    }
  }
  return fallback;
}

function getRuntimeToken(): string | undefined {
  const browserToken = getBrowserAccessToken();
  if (browserToken) {
    return browserToken;
  }
  return process.env.NEXT_PUBLIC_API_TOKEN;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = buildUrl(path);
  const headers = new Headers(init.headers);
  const apiToken = getRuntimeToken();

  const isFormDataBody = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !headers.has("Content-Type") && !isFormDataBody) {
    headers.set("Content-Type", "application/json");
  }
  if (apiToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${apiToken}`);
  }

  const response = await fetch(url, { credentials: "include", ...init, headers });
  const contentType = response.headers.get("content-type") ?? "";

  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => null);
  } else {
    payload = await response.text().catch(() => null);
  }

  if (!response.ok) {
    const message = getErrorMessage(payload, response.statusText);
    throw new ApiError(response.status, message, payload);
  }

  return payload as T;
}

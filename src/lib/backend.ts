import { getBackendRuntimeConfig, type BackendConfigSource } from "@/lib/env";

const HEALTH_PATHS = ["/health", "/api/health", "/api/v1/health", "/healthz"] as const;
const REQUEST_TIMEOUT_MS = 4000;

export type BackendHealth = {
  connected: boolean;
  endpointTried: string | null;
  details: string;
  configuredBaseUrl: string | null;
  source: BackendConfigSource;
};

export function getBackendBaseUrl(): string | null {
  return getBackendRuntimeConfig().baseUrl;
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      method: "GET",
      cache: "no-store",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchBackend(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const { baseUrl, validationMessage } = getBackendRuntimeConfig();

  if (!baseUrl) {
    throw new Error(validationMessage ?? "Backend URL is not configured.");
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return fetchWithTimeout(`${baseUrl}${normalizedPath}`, init, timeoutMs);
}

export async function probeBackendHealth(): Promise<BackendHealth> {
  const { baseUrl, source, validationMessage } = getBackendRuntimeConfig();

  if (!baseUrl) {
    return {
      connected: false,
      endpointTried: null,
      details:
        validationMessage ??
        "Backend URL is not configured. Set NEXT_PUBLIC_BACKEND_URL (and optionally BACKEND_INTERNAL_URL).",
      configuredBaseUrl: null,
      source,
    };
  }

  let lastStatus: number | null = null;

  for (const path of HEALTH_PATHS) {
    const endpoint = `${baseUrl}${path}`;

    try {
      const response = await fetchWithTimeout(endpoint);
      lastStatus = response.status;

      if (response.ok) {
        return {
          connected: true,
          endpointTried: endpoint,
          details: `Health check succeeded with status ${response.status}.`,
          configuredBaseUrl: baseUrl,
          source,
        };
      }
    } catch {
      // Continue trying known health paths.
    }
  }

  const statusDetails = lastStatus
    ? ` Last non-success HTTP status: ${lastStatus}.`
    : " No successful HTTP response was received.";

  return {
    connected: false,
    endpointTried: `${baseUrl}${HEALTH_PATHS[0]}`,
    details:
      `Unable to reach backend health endpoints.${statusDetails} Verify Container App ingress, DNS, and environment variables.`,
    configuredBaseUrl: baseUrl,
    source,
  };
}

const PUBLIC_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;
const INTERNAL_BACKEND_URL = process.env.BACKEND_INTERNAL_URL;

const HEALTH_PATHS = ["/health", "/api/health", "/api/v1/health", "/healthz"] as const;
const REQUEST_TIMEOUT_MS = 4000;

export type BackendHealth = {
  connected: boolean;
  endpointTried: string | null;
  details: string;
};

function buildBaseUrl(): string | null {
  const rawBaseUrl = INTERNAL_BACKEND_URL ?? PUBLIC_BACKEND_URL;

  if (!rawBaseUrl) {
    return null;
  }

  return rawBaseUrl.endsWith("/") ? rawBaseUrl.slice(0, -1) : rawBaseUrl;
}

export function getBackendBaseUrl(): string | null {
  return buildBaseUrl();
}

async function fetchWithTimeout(url: string): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    return await fetch(url, {
      method: "GET",
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function probeBackendHealth(): Promise<BackendHealth> {
  const baseUrl = buildBaseUrl();

  if (!baseUrl) {
    return {
      connected: false,
      endpointTried: null,
      details:
        "Backend URL is not configured. Set NEXT_PUBLIC_BACKEND_URL (and optionally BACKEND_INTERNAL_URL).",
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
  };
}

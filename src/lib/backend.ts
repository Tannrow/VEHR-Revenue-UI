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

/**
 * Returns the public-facing backend URL (NEXT_PUBLIC_BACKEND_URL only).
 * Use this for display purposes to avoid leaking BACKEND_INTERNAL_URL.
 */
export function getPublicBackendUrl(): string | null {
  if (!PUBLIC_BACKEND_URL) {
    return null;
  }
  return PUBLIC_BACKEND_URL.endsWith("/")
    ? PUBLIC_BACKEND_URL.slice(0, -1)
    : PUBLIC_BACKEND_URL;
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

type HealthProbeResult = {
  endpoint: string;
  status: number | null;
  ok: boolean;
};

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

  const healthChecks: Promise<HealthProbeResult>[] = HEALTH_PATHS.map(
    async (path) => {
      const endpoint = `${baseUrl}${path}`;
      try {
        const response = await fetchWithTimeout(endpoint);
        return { endpoint, status: response.status, ok: response.ok };
      } catch {
        return { endpoint, status: null, ok: false };
      }
    },
  );

  const results = await Promise.all(healthChecks);

  const successful = results.find((r) => r.ok);
  if (successful) {
    return {
      connected: true,
      endpointTried: successful.endpoint,
      details: `Health check succeeded with status ${successful.status}.`,
    };
  }

  const lastWithStatus = results.findLast((r) => r.status !== null);
  const lastStatus = lastWithStatus?.status ?? null;
  const lastEndpoint =
    lastWithStatus?.endpoint ?? results[results.length - 1]?.endpoint ?? null;

  const statusDetails =
    lastStatus !== null
      ? ` Last non-success HTTP status: ${lastStatus}.`
      : " No successful HTTP response was received.";

  return {
    connected: false,
    endpointTried: lastEndpoint,
    details: `Unable to reach backend health endpoints.${statusDetails} Verify Container App ingress, DNS, and environment variables.`,
  };
}

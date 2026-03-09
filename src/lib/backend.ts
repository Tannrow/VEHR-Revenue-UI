const DEFAULT_ACCEPT_HEADER = "application/json";
const ERROR_TEXT_LIMIT = 500;

function normalizeBaseUrl(value: string | undefined): string | null {
  const trimmedValue = value?.trim();

  if (!trimmedValue) {
    return null;
  }

  return trimmedValue.endsWith("/") ? trimmedValue.slice(0, -1) : trimmedValue;
}

export function getBackendBaseUrl(): string {
  const baseUrl =
    normalizeBaseUrl(process.env.NEXT_PUBLIC_API_URL) ??
    normalizeBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);

  if (!baseUrl) {
    throw new Error("Backend URL is not configured. Set NEXT_PUBLIC_API_URL or NEXT_PUBLIC_API_BASE_URL.");
  }

  return baseUrl;
}

function getBackendUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${getBackendBaseUrl()}${normalizedPath}`;
}

function createProxyHeaders(contentType: string | null): HeadersInit | undefined {
  return contentType ? { "content-type": contentType } : undefined;
}

function trimResponseText(value: string): string {
  const trimmedValue = value.trim();

  if (trimmedValue.length <= ERROR_TEXT_LIMIT) {
    return trimmedValue;
  }

  return `${trimmedValue.slice(0, ERROR_TEXT_LIMIT)}…`;
}

export class BackendFetchError extends Error {
  status: number;
  responseText: string;
  contentType: string | null;

  constructor(status: number, responseText: string, contentType: string | null) {
    super(`Backend request failed with status ${status}${responseText ? `: ${responseText}` : ""}`);
    this.name = "BackendFetchError";
    this.status = status;
    this.responseText = responseText;
    this.contentType = contentType;
  }
}

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);

  if (!headers.has("Accept")) {
    headers.set("Accept", DEFAULT_ACCEPT_HEADER);
  }

  const response = await fetch(getBackendUrl(path), {
    ...init,
    headers,
    cache: init.cache ?? "no-store",
  });

  if (response.ok) {
    return response;
  }

  throw new BackendFetchError(
    response.status,
    trimResponseText(await response.text()),
    response.headers.get("content-type"),
  );
}

export async function proxyBackendResponse(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    const response = await backendFetch(path, init);

    return new Response(await response.text(), {
      status: response.status,
      headers: createProxyHeaders(response.headers.get("content-type")),
    });
  } catch (error) {
    if (error instanceof BackendFetchError) {
      return new Response(error.responseText, {
        status: error.status,
        headers: createProxyHeaders(error.contentType),
      });
    }

    throw error;
  }
}

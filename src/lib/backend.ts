const DEFAULT_TIMEOUT_MS = 10_000;
const ERROR_TEXT_LIMIT = 400;
const OPENAPI_PATH = "/openapi.json";

type BackendFetchOptions = {
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  cache?: RequestCache;
};

type OpenApiOperation = {
  operationId?: string;
  summary?: string;
  description?: string;
  tags?: string[];
  requestBody?: {
    content?: Record<string, unknown>;
  };
};

type OpenApiPathItem = Partial<Record<Lowercase<string>, OpenApiOperation>>;

type OpenApiDocument = {
  paths?: Record<string, OpenApiPathItem>;
};

type EndpointDiscoveryOptions = {
  method: "get" | "post";
  preferredPaths: readonly string[];
  keywords: readonly string[];
  requireMultipart?: boolean;
};

function normalizeUrl(value: string | undefined): string | null {
  const trimmed = value?.trim();

  if (!trimmed) {
    return null;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

function getConfiguredBackendBaseUrl(): string | null {
  return (
    normalizeUrl(process.env.NEXT_PUBLIC_API_URL) ??
    normalizeUrl(process.env.NEXT_PUBLIC_API_BASE_URL) ??
    normalizeUrl(process.env.BACKEND_INTERNAL_URL) ??
    normalizeUrl(process.env.NEXT_PUBLIC_BACKEND_URL)
  );
}

function getBackendUrl(path: string): string {
  const baseUrl = getConfiguredBackendBaseUrl();

  if (!baseUrl) {
    throw new Error(
      "Backend URL is not configured. Set NEXT_PUBLIC_API_URL or NEXT_PUBLIC_API_BASE_URL.",
    );
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${baseUrl}${normalizedPath}`;
}

async function readResponseText(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}

function truncateText(value: string): string {
  if (value.length <= ERROR_TEXT_LIMIT) {
    return value;
  }

  return `${value.slice(0, ERROR_TEXT_LIMIT)}…`;
}

async function requestBackend(
  path: string,
  { method = "GET", headers, body, cache = "no-store" }: BackendFetchOptions = {},
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    return await fetch(getBackendUrl(path), {
      method,
      headers: {
        Accept: "application/json",
        ...(headers ?? {}),
      },
      body,
      cache,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function backendFetch(
  path: string,
  options: BackendFetchOptions = {},
): Promise<Response> {
  const response = await requestBackend(path, options);

  if (response.ok) {
    return response;
  }

  const responseText = truncateText(await readResponseText(response));

  throw new Error(
    `Backend request failed (${response.status}) for ${path}: ${responseText || "No response body."}`,
  );
}

export function getBackendBaseUrl(): string | null {
  return getConfiguredBackendBaseUrl();
}

let openApiDocumentPromise: Promise<OpenApiDocument | null> | null = null;

async function getOpenApiDocument(): Promise<OpenApiDocument | null> {
  if (!openApiDocumentPromise) {
    openApiDocumentPromise = (async () => {
      try {
        const response = await backendFetch(OPENAPI_PATH, { cache: "force-cache" });
        return (await response.json()) as OpenApiDocument;
      } catch {
        return null;
      }
    })();
  }

  return openApiDocumentPromise;
}

function getOperationText(path: string, operation: OpenApiOperation | undefined): string {
  return [
    path,
    operation?.operationId,
    operation?.summary,
    operation?.description,
    ...(operation?.tags ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function scoreOperation(
  path: string,
  operation: OpenApiOperation | undefined,
  keywords: readonly string[],
): number {
  if (!operation || path.includes("{")) {
    return -1;
  }

  const haystack = getOperationText(path, operation);

  return keywords.reduce((score, keyword) => {
    if (!haystack.includes(keyword)) {
      return score;
    }

    return score + (path === `/${keyword}` ? 5 : path.includes(keyword) ? 3 : 1);
  }, 0);
}

function hasMultipartRequestBody(operation: OpenApiOperation | undefined): boolean {
  return Boolean(operation?.requestBody?.content?.["multipart/form-data"]);
}

export async function discoverBackendPath({
  method,
  preferredPaths,
  keywords,
  requireMultipart = false,
}: EndpointDiscoveryOptions): Promise<string> {
  const openApiDocument = await getOpenApiDocument();
  const paths = openApiDocument?.paths ?? {};

  for (const path of preferredPaths) {
    const operation = paths[path]?.[method];

    if (!operation) {
      continue;
    }

    if (requireMultipart && !hasMultipartRequestBody(operation)) {
      continue;
    }

    return path;
  }

  let bestPath: string | null = null;
  let bestScore = -1;

  for (const [path, pathItem] of Object.entries(paths)) {
    const operation = pathItem[method];

    if (requireMultipart && !hasMultipartRequestBody(operation)) {
      continue;
    }

    const score = scoreOperation(path, operation, keywords);

    if (score > bestScore) {
      bestScore = score;
      bestPath = path;
    }
  }

  if (bestPath) {
    return bestPath;
  }

  return preferredPaths[0];
}

export async function proxyBackendGet(path: string): Promise<Response> {
  const response = await requestBackend(path, { method: "GET" });
  const contentType = response.headers.get("content-type") ?? "text/plain; charset=utf-8";
  const body = await response.text();

  return new Response(body, {
    status: response.status,
    headers: {
      "content-type": contentType,
    },
  });
}

export async function proxyBackendMultipartPost(path: string, formData: FormData): Promise<Response> {
  const response = await requestBackend(path, {
    method: "POST",
    body: formData,
  });
  const contentType = response.headers.get("content-type") ?? "text/plain; charset=utf-8";
  const body = await response.text();

  return new Response(body, {
    status: response.status,
    headers: {
      "content-type": contentType,
    },
  });
}

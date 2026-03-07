export type BackendConfigSource = "internal" | "public" | "none";

export type BackendRuntimeConfig = {
  baseUrl: string | null;
  source: BackendConfigSource;
  validationMessage: string | null;
};

function normalizeUrl(value: string | undefined): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();

  if (!trimmed) {
    return null;
  }

  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

function isAbsoluteUrl(value: string): boolean {
  try {
    const url = new URL(value);

    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function getBackendRuntimeConfig(): BackendRuntimeConfig {
  const internalUrl = normalizeUrl(process.env.BACKEND_INTERNAL_URL);
  const publicUrl = normalizeUrl(process.env.NEXT_PUBLIC_BACKEND_URL);

  const baseUrl = internalUrl ?? publicUrl;
  const source: BackendConfigSource = internalUrl ? "internal" : publicUrl ? "public" : "none";

  if (!baseUrl) {
    return {
      baseUrl: null,
      source,
      validationMessage:
        "Backend URL is not configured. Set NEXT_PUBLIC_BACKEND_URL (and optionally BACKEND_INTERNAL_URL).",
    };
  }

  if (!isAbsoluteUrl(baseUrl)) {
    return {
      baseUrl: null,
      source,
      validationMessage: `Configured backend URL must be an absolute http(s) URL. Received "${baseUrl}".`,
    };
  }

  return {
    baseUrl,
    source,
    validationMessage: null,
  };
}

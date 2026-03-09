import { headers } from "next/headers";

function getProtocol(host: string, forwardedProtocol: string | null): string {
  if (forwardedProtocol) {
    return forwardedProtocol;
  }

  return host.includes("localhost") || host.startsWith("127.0.0.1") ? "http" : "https";
}

async function getSameOriginUrl(path: string): Promise<string> {
  const headerStore = await headers();
  const host = headerStore.get("x-forwarded-host") ?? headerStore.get("host");

  if (!host) {
    throw new Error("Unable to determine the current request host.");
  }

  const protocol = getProtocol(host, headerStore.get("x-forwarded-proto"));
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${protocol}://${host}${normalizedPath}`;
}

export type InternalApiResponse = {
  ok: boolean;
  status: number;
  contentType: string;
  data: unknown;
  text: string;
};

export async function fetchInternal(path: string): Promise<InternalApiResponse> {
  const response = await fetch(await getSameOriginUrl(path), {
    cache: "no-store",
  });
  const contentType = response.headers.get("content-type") ?? "";
  const text = await response.text();

  let data: unknown = null;

  if (contentType.includes("application/json") && text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  }

  return {
    ok: response.ok,
    status: response.status,
    contentType,
    data,
    text,
  };
}

export async function fetchInternalJson<T>(path: string): Promise<T> {
  const response = await fetchInternal(path);

  if (!response.contentType.includes("application/json")) {
    throw new Error(`Request to ${path} did not return JSON.`);
  }

  const payload = response.data as T;

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
        ? payload.error
        : `Request to ${path} failed with status ${response.status}.`;

    throw new Error(message);
  }

  return payload;
}

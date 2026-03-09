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

export async function fetchInternalJson<T>(path: string): Promise<T> {
  const response = await fetch(await getSameOriginUrl(path), {
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? ((await response.json()) as T)
    : (({ text: await response.text() } satisfies Record<string, unknown>) as T);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
        ? payload.error
        : `Request to ${path} failed with status ${response.status}.`;

    throw new Error(message);
  }

  return payload;
}

import { isFetchFailedMessage } from "@/lib/error-messages";

export type ApiClientResponse = {
  ok: boolean;
  status: number;
  contentType: string;
  data: unknown;
  text: string;
};

export type ApiFailureTelemetry = {
  route: string;
  status?: number;
  reason: string;
  detail?: string;
};

export async function apiClientFetch(path: string, init?: RequestInit): Promise<ApiClientResponse> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers: new Headers({
      accept: "application/json",
      ...(init?.headers ? Object.fromEntries(new Headers(init.headers).entries()) : {}),
    }),
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

export function logApiFailure({ route, status, reason, detail }: ApiFailureTelemetry): void {
  const normalizedReason = isFetchFailedMessage(reason) ? "fetch failed" : reason;
  const payload = {
    route,
    status,
    reason: normalizedReason,
    detail,
  };

  if (status === 404) {
    console.warn("[telemetry] API request did not return a snapshot", payload);
    return;
  }

  console.error("[telemetry] API request failed", payload);
}

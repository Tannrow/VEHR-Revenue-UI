import { getBrowserAccessToken } from "@/lib/auth";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export type EmbedConfigResponse = {
  type: "report";
  embedUrl: string;
  accessToken: string;
  reportId: string;
  tokenExpiry?: string | null;
  expiresOn?: string | null;
};

function apiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return (configured || DEFAULT_API_BASE_URL).replace(/\/$/, "");
}

function describeErrorPayload(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((item) => String(item)).join("; ");
    }
  }
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }
  return "Unable to fetch embed configuration.";
}

export async function fetchEmbedConfig(reportKey: string): Promise<EmbedConfigResponse> {
  const requestUrl = `${apiBaseUrl()}/api/v1/bi/embed-config?report_key=${encodeURIComponent(reportKey)}`;

  const headers = new Headers({ "Content-Type": "application/json" });
  const accessToken = getBrowserAccessToken();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(requestUrl, {
    method: "GET",
    cache: "no-store",
    credentials: "include",
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => null);
  } else {
    payload = await response.text().catch(() => null);
  }

  if (!response.ok) {
    const detail = describeErrorPayload(payload);
    throw new Error(`Embed config request failed (${response.status}): ${detail}`);
  }

  if (!payload || typeof payload !== "object") {
    throw new Error("Embed config response was not valid JSON.");
  }

  const reportId = String((payload as { reportId?: unknown }).reportId ?? "").trim();
  const embedUrl = String((payload as { embedUrl?: unknown }).embedUrl ?? "").trim();
  const embedAccessToken = String((payload as { accessToken?: unknown }).accessToken ?? "").trim();
  if (!reportId || !embedUrl || !embedAccessToken) {
    throw new Error("Embed config response is missing required fields.");
  }

  const tokenExpiryRaw = (payload as { tokenExpiry?: unknown }).tokenExpiry;
  const expiresOnRaw = (payload as { expiresOn?: unknown }).expiresOn;
  return {
    type: "report",
    reportId,
    embedUrl,
    accessToken: embedAccessToken,
    tokenExpiry: typeof tokenExpiryRaw === "string" && tokenExpiryRaw.trim() ? tokenExpiryRaw : null,
    expiresOn: typeof expiresOnRaw === "string" && expiresOnRaw.trim() ? expiresOnRaw : null,
  };
}

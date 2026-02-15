import { apiFetch } from "@/lib/api";

export type ReportListItem = {
  report_key: string;
  name?: string;
};

export type EmbedConfigResponse = {
  type: "report" | "dashboard" | "tile";
  embedUrl: string;
  accessToken: string;
  reportId?: string;
  tokenExpiry?: string | null;
  expiresOn?: string | null;
};

export async function fetchReports(): Promise<ReportListItem[]> {
  const payload = await apiFetch<unknown>("/api/v1/bi/reports", { cache: "no-store" });
  if (!Array.isArray(payload)) {
    throw new Error("Reports response was not an array.");
  }

  const reports: ReportListItem[] = [];
  for (const row of payload) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const reportKeyRaw = (row as { report_key?: unknown; key?: unknown }).report_key
      ?? (row as { key?: unknown }).key;
    const reportKey = String(reportKeyRaw ?? "").trim();
    if (!reportKey) {
      continue;
    }
    const nameRaw = (row as { name?: unknown }).name;
    const name = typeof nameRaw === "string" && nameRaw.trim() ? nameRaw : undefined;
    reports.push({
      report_key: reportKey,
      ...(name ? { name } : {}),
    });
  }
  return reports;
}

export async function fetchEmbedConfig(reportKey: string): Promise<EmbedConfigResponse> {
  const payload = await apiFetch<unknown>(
    `/api/v1/bi/embed-config?report_key=${encodeURIComponent(reportKey)}`,
    { cache: "no-store" },
  );
  if (!payload || typeof payload !== "object") {
    throw new Error("Embed config response was not valid JSON.");
  }

  const reportIdRaw = (payload as { reportId?: unknown }).reportId;
  const embedUrl = String((payload as { embedUrl?: unknown }).embedUrl ?? "").trim();
  const embedAccessToken = String((payload as { accessToken?: unknown }).accessToken ?? "").trim();
  if (!embedUrl || !embedAccessToken) {
    throw new Error("Embed config response is missing required fields.");
  }

  const tokenExpiryRaw = (payload as { tokenExpiry?: unknown }).tokenExpiry;
  const expiresOnRaw = (payload as { expiresOn?: unknown }).expiresOn;
  const typeRaw = String((payload as { type?: unknown }).type ?? "report").toLowerCase();
  const type: "report" | "dashboard" | "tile" =
    typeRaw === "dashboard" || typeRaw === "tile" ? typeRaw : "report";

  return {
    type,
    reportId: typeof reportIdRaw === "string" && reportIdRaw.trim() ? reportIdRaw : undefined,
    embedUrl,
    accessToken: embedAccessToken,
    tokenExpiry: typeof tokenExpiryRaw === "string" && tokenExpiryRaw.trim() ? tokenExpiryRaw : null,
    expiresOn: typeof expiresOnRaw === "string" && expiresOnRaw.trim() ? expiresOnRaw : null,
  };
}

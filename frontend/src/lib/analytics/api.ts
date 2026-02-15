import { apiFetch } from "@/lib/api";

export type AnalyticsMetricRead = {
  metric_key: string;
  description?: string | null;
  category: string;
  grain: string;
  backing_table: string;
};

export type AnalyticsQueryRow = {
  kpi_date?: string | null;
  as_of_ts?: string | null;
  value_num?: number | null;
  value_json?: unknown;
  facility_id?: string | null;
  program_id?: string | null;
  provider_id?: string | null;
  payer_id?: string | null;
};

export type AnalyticsQueryResponse = {
  metric_key: string;
  grain: string;
  start?: string | null;
  end?: string | null;
  rows: AnalyticsQueryRow[];
};

export async function fetchAnalyticsMetrics(): Promise<AnalyticsMetricRead[]> {
  return apiFetch<AnalyticsMetricRead[]>("/api/v1/analytics/metrics", { cache: "no-store" });
}

export type AnalyticsQueryParams = {
  start?: string;
  end?: string;
  facility_id?: string;
  program_id?: string;
  provider_id?: string;
  payer_id?: string;
};

export async function queryAnalyticsMetric(metricKey: string, params: AnalyticsQueryParams = {}): Promise<AnalyticsQueryResponse> {
  const sp = new URLSearchParams();
  sp.set("metric_key", metricKey);
  if (params.start) sp.set("start", params.start);
  if (params.end) sp.set("end", params.end);
  if (params.facility_id) sp.set("facility_id", params.facility_id);
  if (params.program_id) sp.set("program_id", params.program_id);
  if (params.provider_id) sp.set("provider_id", params.provider_id);
  if (params.payer_id) sp.set("payer_id", params.payer_id);

  return apiFetch<AnalyticsQueryResponse>(`/api/v1/analytics/query?${sp.toString()}`, { cache: "no-store" });
}


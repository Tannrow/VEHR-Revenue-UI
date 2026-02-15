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

export type AnalyticsAlertRead = {
  id: string;
  organization_id: string;
  alert_type: string;
  metric_key?: string | null;
  report_key?: string | null;
  baseline_window_days: number;
  comparison_period: string;
  current_range_start: string;
  current_range_end: string;
  baseline_range_start: string;
  baseline_range_end: string;
  current_value: number;
  baseline_value: number;
  delta_value: number;
  delta_pct?: number | null;
  severity: string;
  title: string;
  summary: string;
  recommended_actions: string[];
  context_filters?: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  dedupe_key: string;
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

export type AnalyticsAlertsQuery = {
  status?: string;
  report_key?: string;
  severity_min?: string;
  since?: string;
  limit?: number;
  offset?: number;
};

export async function fetchAnalyticsAlerts(params: AnalyticsAlertsQuery = {}): Promise<AnalyticsAlertRead[]> {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.report_key) sp.set("report_key", params.report_key);
  if (params.severity_min) sp.set("severity_min", params.severity_min);
  if (params.since) sp.set("since", params.since);
  if (typeof params.limit === "number") sp.set("limit", String(params.limit));
  if (typeof params.offset === "number") sp.set("offset", String(params.offset));

  const suffix = sp.toString();
  return apiFetch<AnalyticsAlertRead[]>(`/api/v1/analytics/alerts${suffix ? `?${suffix}` : ""}`, { cache: "no-store" });
}

export async function acknowledgeAnalyticsAlert(alertId: string): Promise<AnalyticsAlertRead> {
  return apiFetch<AnalyticsAlertRead>(`/api/v1/analytics/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
    method: "POST",
    cache: "no-store",
  });
}

export async function resolveAnalyticsAlert(alertId: string): Promise<AnalyticsAlertRead> {
  return apiFetch<AnalyticsAlertRead>(`/api/v1/analytics/alerts/${encodeURIComponent(alertId)}/resolve`, {
    method: "POST",
    cache: "no-store",
  });
}

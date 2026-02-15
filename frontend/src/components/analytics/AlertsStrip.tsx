"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchAnalyticsAlerts, type AnalyticsAlertRead } from "@/lib/analytics/api";

type AlertsStripProps = {
  reportKey?: string;
  limit?: number;
  onSelectAlert?: (alert: AnalyticsAlertRead) => void;
};

function severityBadgeClass(severity: string): string {
  const normalized = (severity ?? "").toLowerCase();
  switch (normalized) {
    case "critical":
      return "border-rose-200 bg-rose-50 text-rose-700";
    case "high":
      return "border-orange-200 bg-orange-50 text-orange-700";
    case "medium":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "low":
      return "border-sky-200 bg-sky-50 text-sky-700";
    case "info":
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function formatDeltaPct(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "";
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${Math.abs(value).toFixed(1)}%`;
}

export default function AlertsStrip({ reportKey, limit = 3, onSelectAlert }: AlertsStripProps) {
  const normalizedReportKey = (reportKey ?? "").trim().toLowerCase();

  const [alerts, setAlerts] = useState<AnalyticsAlertRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    return {
      status: "open",
      report_key: normalizedReportKey || undefined,
      limit,
    };
  }, [limit, normalizedReportKey]);

  useEffect(() => {
    let isMounted = true;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const rows = await fetchAnalyticsAlerts(query);
        if (!isMounted) return;
        setAlerts(rows);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Unable to load alerts.");
        setAlerts([]);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    void load();
    return () => {
      isMounted = false;
    };
  }, [query]);

  if (isLoading) {
    return (
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
        <div className="h-4 w-44 animate-pulse rounded bg-slate-100" />
        <div className="mt-4 space-y-3">
          {Array.from({ length: Math.max(1, limit) }).map((_, index) => (
            <div key={`alert-skel-${index}`} className="h-16 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
        Alerts unavailable: {error}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
        No open alerts right now.
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Alerts</p>
          <p className="mt-1 text-sm text-slate-600">Top open anomalies detected from KPI baselines.</p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {alerts.map((alert) => {
          return (
            <div
              key={alert.id}
              className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:bg-slate-50 md:flex-row md:items-start md:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={severityBadgeClass(alert.severity)}>
                    {alert.severity}
                  </Badge>
                  {alert.metric_key ? (
                    <span className="text-xs font-medium text-slate-500">{alert.metric_key}</span>
                  ) : null}
                  {typeof alert.delta_pct === "number" ? (
                    <span className="text-xs font-semibold text-slate-700">{formatDeltaPct(alert.delta_pct)}</span>
                  ) : null}
                </div>

                <p className="mt-2 truncate text-sm font-semibold text-slate-900">{alert.title}</p>
                <p className="mt-1 line-clamp-2 text-sm text-slate-600">{alert.summary}</p>
              </div>

              {onSelectAlert ? (
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      onSelectAlert(alert);
                    }}
                  >
                    View in EI
                  </Button>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}


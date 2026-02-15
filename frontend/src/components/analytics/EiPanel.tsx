"use client";

import { Loader2, Send, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  acknowledgeAnalyticsAlert,
  fetchAnalyticsAlerts,
  fetchAnalyticsMetrics,
  queryAnalyticsMetric,
  resolveAnalyticsAlert,
  type AnalyticsAlertRead,
  type AnalyticsMetricRead,
  type AnalyticsQueryRow,
} from "@/lib/analytics/api";
import { defaultKpisForReport } from "@/lib/analytics/catalog";

type EiPanelProps = {
  open: boolean;
  onClose: () => void;
  reportKey: string;
  reportTitle: string;
  initialAlert?: AnalyticsAlertRead | null;
};

type EiFilters = {
  start: string;
  end: string;
  facility_id?: string;
  program_id?: string;
  provider_id?: string;
  payer_id?: string;
};

type EiMessage =
  | {
    id: string;
    role: "user";
    content: string;
    createdAt: number;
  }
  | {
    id: string;
    role: "ei";
    status: "loading" | "done" | "error";
    content: string;
    createdAt: number;
    metricKeysUsed: string[];
    filters: EiFilters | null;
    suggestedNextActions: string[];
  };

type AlertStatusFilter = "open" | "acknowledged" | "resolved";

function formatDateYmd(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfWeekMonday(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayOfWeek = d.getDay();
  const daysSinceMonday = (dayOfWeek + 6) % 7;
  d.setDate(d.getDate() - daysSinceMonday);
  return d;
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  d.setDate(d.getDate() + days);
  return d;
}

function titleCaseFromKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function isRateMetric(metricKey: string): boolean {
  return metricKey.toLowerCase().includes("rate");
}

function formatMetricValue(metricKey: string, value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  if (isRateMetric(metricKey)) {
    const ratio = value <= 1 ? value * 100 : value;
    return `${ratio.toFixed(1)}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function numericValues(rows: AnalyticsQueryRow[]): number[] {
  return rows
    .map((row) => row.value_num)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
}

function aggregate(metricKey: string, rows: AnalyticsQueryRow[]): number | null {
  const values = numericValues(rows);
  if (values.length === 0) return null;
  if (isRateMetric(metricKey)) {
    const sum = values.reduce((acc, value) => acc + value, 0);
    return sum / values.length;
  }
  return values.reduce((acc, value) => acc + value, 0);
}

function rowsInWindow(rows: AnalyticsQueryRow[], start: Date, end: Date): AnalyticsQueryRow[] {
  const startMs = start.getTime();
  const endMs = end.getTime();
  return rows.filter((row) => {
    const raw = row.kpi_date ?? row.as_of_ts;
    if (!raw) return false;
    const parsed = new Date(raw);
    const candidate = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate()).getTime();
    return candidate >= startMs && candidate <= endMs;
  });
}

function selectMetricKeys(
  question: string,
  availableKeys: Set<string>,
  defaults: string[],
): string[] {
  const normalized = question.toLowerCase();
  const selected: string[] = [];

  // Direct metric_key mention.
  for (const key of availableKeys) {
    if (normalized.includes(key.toLowerCase())) {
      selected.push(key);
    }
  }

  const keywordMap: Array<{ test: RegExp; metric: string }> = [
    { test: /(census|active)/, metric: "active_clients" },
    { test: /encounter/, metric: "encounters_week" },
    { test: /charge/, metric: "charges_week" },
    { test: /(paid|payment)/, metric: "claims_paid_week" },
    { test: /submit/, metric: "claims_submitted_week" },
    { test: /denial/, metric: "denial_rate_week" },
    { test: /(accounts receivable|\\bar\\b)/, metric: "ar_balance_total" },
    { test: /unsigned/, metric: "unsigned_notes_over_72h" },
    { test: /admission/, metric: "new_admissions_week" },
    { test: /discharge/, metric: "discharges_week" },
    { test: /no\\s*show/, metric: "no_show_rate_week" },
    { test: /attendance/, metric: "attendance_rate_week" },
  ];

  for (const mapping of keywordMap) {
    if (mapping.test.test(normalized) && availableKeys.has(mapping.metric)) {
      selected.push(mapping.metric);
    }
  }

  const deduped = Array.from(new Set(selected.map((item) => item.trim()).filter(Boolean)));
  const fallback = defaults.filter((item) => availableKeys.has(item));
  return (deduped.length > 0 ? deduped : fallback).slice(0, 3);
}

function suggestedActionsForMetric(metricKey: string): string[] {
  const key = metricKey.toLowerCase();
  if (key.includes("denial_rate")) {
    return [
      "Review denied claims for trends by payer and service date.",
      "Validate eligibility and authorization checks for the top denial cohort.",
    ];
  }
  if (key.startsWith("ar_") || key.includes("ar_balance")) {
    return [
      "Prioritize follow-up on aging AR buckets and confirm submission cadence.",
      "Validate payment posting timelines and investigate stalled claims.",
    ];
  }
  if (key.includes("unsigned")) {
    return [
      "Route unsigned documentation to responsible staff and monitor SLA compliance.",
      "Confirm escalation rules for notes exceeding 72 hours.",
    ];
  }
  if (key.includes("encounters")) {
    return [
      "Cross-check scheduling and staffing coverage for low-volume days.",
      "Investigate drivers behind week-over-week encounter shifts.",
    ];
  }
  if (key.includes("attendance") || key.includes("no_show")) {
    return [
      "Review appointment reminders and outreach workflow for high no-show cohorts.",
      "Validate transportation and access barriers by facility/program.",
    ];
  }
  return ["Validate metric movement by slicing facility and program, then determine owners for next actions."];
}

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

export default function EiPanel({ open, onClose, reportKey, reportTitle, initialAlert }: EiPanelProps) {
  const [metrics, setMetrics] = useState<AnalyticsMetricRead[] | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<AnalyticsAlertRead[]>([]);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsStatus, setAlertsStatus] = useState<AlertStatusFilter>("open");
  const [alertsWindow, setAlertsWindow] = useState<"all" | 7 | 30 | 90>("all");
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertActionBusyId, setAlertActionBusyId] = useState<string | null>(null);
  const [messages, setMessages] = useState<EiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);

  const chatRef = useRef<HTMLDivElement | null>(null);
  const lastInjectedAlertRef = useRef<string | null>(null);

  const availableMetricKeys = useMemo(() => new Set((metrics ?? []).map((row) => row.metric_key)), [metrics]);
  const defaultKpis = useMemo(() => defaultKpisForReport(reportKey), [reportKey]);

  function injectAlertContext(alert: AnalyticsAlertRead) {
    const now = Date.now();
    const metricKey = alert.metric_key ?? "";
    const contentLines = [
      `Alert: ${alert.title}`,
      "",
      alert.summary,
      "",
      alert.recommended_actions?.length
        ? `Recommended actions:\n- ${alert.recommended_actions.join("\n- ")}`
        : "Recommended actions: none",
    ];

    const eiMessage: EiMessage = {
      id: `ei-alert-${now}`,
      role: "ei",
      status: "done",
      content: contentLines.join("\n"),
      createdAt: now,
      metricKeysUsed: metricKey ? [metricKey] : [],
      filters: {
        start: alert.current_range_start,
        end: alert.current_range_end,
      },
      suggestedNextActions: alert.recommended_actions ?? [],
    };

    setMessages((current) => [...current, eiMessage]);
  }

  const visibleAlerts = useMemo(() => {
    if (alertsWindow === "all") return alerts;
    return alerts.filter((row) => row.baseline_window_days === alertsWindow);
  }, [alerts, alertsWindow]);

  useEffect(() => {
    if (!open) {
      lastInjectedAlertRef.current = null;
      return;
    }
    let isMounted = true;

    async function loadMetrics() {
      setMetricsError(null);
      try {
        const rows = await fetchAnalyticsMetrics();
        if (!isMounted) return;
        setMetrics(rows);
      } catch (error) {
        if (!isMounted) return;
        setMetricsError(error instanceof Error ? error.message : "Unable to load analytics metrics.");
        setMetrics([]);
      }
    }

    void loadMetrics();
    return () => {
      isMounted = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let isMounted = true;

    async function loadAlerts() {
      setAlertsLoading(true);
      setAlertsError(null);
      try {
        const rows = await fetchAnalyticsAlerts({ status: alertsStatus, limit: 20 });
        if (!isMounted) return;
        setAlerts(rows);
      } catch (error) {
        if (!isMounted) return;
        setAlertsError(error instanceof Error ? error.message : "Unable to load alerts.");
        setAlerts([]);
      } finally {
        if (isMounted) setAlertsLoading(false);
      }
    }

    void loadAlerts();
    return () => {
      isMounted = false;
    };
  }, [alertsStatus, open]);

  useEffect(() => {
    if (!open) return;
    if (!initialAlert) return;
    if (lastInjectedAlertRef.current === initialAlert.id) return;
    lastInjectedAlertRef.current = initialAlert.id;
    injectAlertContext(initialAlert);
  }, [initialAlert, open]);

  useEffect(() => {
    if (!open) return;
    const node = chatRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, open]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const now = Date.now();
    const userMessage: EiMessage = {
      id: `user-${now}`,
      role: "user",
      content: trimmed,
      createdAt: now,
    };

    const placeholder: EiMessage = {
      id: `ei-${now}`,
      role: "ei",
      status: "loading",
      content: "Analyzing metrics...",
      createdAt: now + 1,
      metricKeysUsed: [],
      filters: null,
      suggestedNextActions: [],
    };

    setMessages((current) => [...current, userMessage, placeholder]);
    setDraft("");
    setIsSending(true);

    const today = new Date();
    const currentStart = startOfWeekMonday(today);
    const currentEnd = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const windowDays = Math.max(1, Math.round((currentEnd.getTime() - currentStart.getTime()) / 86400000) + 1);
    const previousStart = addDays(currentStart, -7);

    const queryStart = formatDateYmd(previousStart);
    const queryEnd = formatDateYmd(currentEnd);

    const metricKeys = selectMetricKeys(trimmed, availableMetricKeys, defaultKpis);

    try {
      const payloads = await Promise.all(
        metricKeys.map((metricKey) =>
          queryAnalyticsMetric(metricKey, { start: queryStart, end: queryEnd }),
        ),
      );

      const lines: string[] = [];
      const nextActions = new Set<string>();

      for (let index = 0; index < payloads.length; index += 1) {
        const metricKey = metricKeys[index];
        const payload = payloads[index];
        const currentRows = rowsInWindow(payload.rows, currentStart, currentEnd);
        const previousEnd = addDays(previousStart, windowDays - 1);
        const previousRows = rowsInWindow(payload.rows, previousStart, previousEnd);

        const currentValue = aggregate(metricKey, currentRows);
        const previousValue = aggregate(metricKey, previousRows);

        let deltaText = "";
        if (previousValue !== null && previousValue !== 0 && currentValue !== null) {
          const deltaPct = (currentValue - previousValue) / Math.abs(previousValue);
          deltaText = ` (${deltaPct >= 0 ? "+" : "-"}${Math.abs(deltaPct * 100).toFixed(1)}% vs prior week)`;
        }

        lines.push(`${titleCaseFromKey(metricKey)}: ${formatMetricValue(metricKey, currentValue)}${deltaText}`);
        for (const action of suggestedActionsForMetric(metricKey)) {
          nextActions.add(action);
        }
      }

      const content = lines.length > 0
        ? `Here are the key signals for ${reportTitle}:\n\n- ${lines.join("\n- ")}`
        : "No KPI values were returned for the selected metrics in this period.";

      const response: EiMessage = {
        id: placeholder.id,
        role: "ei",
        status: "done",
        content,
        createdAt: placeholder.createdAt,
        metricKeysUsed: metricKeys,
        filters: {
          start: queryStart,
          end: queryEnd,
        },
        suggestedNextActions: Array.from(nextActions).slice(0, 6),
      };

      setMessages((current) =>
        current.map((msg) => (msg.id === placeholder.id ? response : msg)),
      );
    } catch (error) {
      console.error("EI panel query failed", error);
      const response: EiMessage = {
        id: placeholder.id,
        role: "ei",
        status: "error",
        content: error instanceof Error ? error.message : "EI request failed.",
        createdAt: placeholder.createdAt,
        metricKeysUsed: metricKeys,
        filters: {
          start: queryStart,
          end: queryEnd,
        },
        suggestedNextActions: [],
      };

      setMessages((current) =>
        current.map((msg) => (msg.id === placeholder.id ? response : msg)),
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close EI panel"
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm transition-opacity ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
      />

      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-[92vw] max-w-[460px] flex-col border-l border-slate-200 bg-white shadow-[0_20px_60px_-30px_rgba(15,23,42,0.5)] transition-transform duration-300 ${open ? "translate-x-0" : "translate-x-full"}`}
        role="dialog"
        aria-modal="true"
        aria-label="EI Insights panel"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">EI Insights</p>
            <p className="mt-1 text-base font-semibold text-slate-900">{reportTitle}</p>
            <p className="mt-1 text-xs text-slate-500">Report key: {reportKey}</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
            <X className="h-5 w-5" />
          </Button>
        </div>

        {metricsError ? (
          <div className="border-b border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-700">
            Metrics catalog unavailable: {metricsError}
          </div>
        ) : null}

        <div ref={chatRef} className="flex-1 overflow-y-auto px-5 py-4">
          <section className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Alerts</p>
                <p className="mt-1 text-sm text-slate-600">Recent KPI anomalies detected from baseline comparisons.</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={alertsStatus}
                  onChange={(event) => setAlertsStatus(event.target.value as AlertStatusFilter)}
                  className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                  aria-label="Alert status filter"
                >
                  <option value="open">Open</option>
                  <option value="acknowledged">Acknowledged</option>
                  <option value="resolved">Resolved</option>
                </select>

                <select
                  value={alertsWindow}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (value === "all") {
                      setAlertsWindow("all");
                    } else {
                      setAlertsWindow(Number(value) as 7 | 30 | 90);
                    }
                  }}
                  className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                  aria-label="Baseline window filter"
                >
                  <option value="all">All windows</option>
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                </select>
              </div>
            </div>

            {alertsError ? (
              <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                Alerts unavailable: {alertsError}
              </div>
            ) : null}

            {alertsLoading ? (
              <div className="mt-3 space-y-2">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={`alerts-loading-${index}`} className="h-14 animate-pulse rounded-lg bg-slate-100" />
                ))}
              </div>
            ) : null}

            {!alertsLoading && !alertsError ? (
              visibleAlerts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {visibleAlerts.map((alert) => {
                    const deltaLabel = formatDeltaPct(alert.delta_pct);
                    const actionsDisabled = alertActionBusyId === alert.id;
                    const canAck = alert.status === "open";
                    const canResolve = alert.status !== "resolved";

                    async function updateAlert(action: "ack" | "resolve") {
                      if (actionsDisabled) return;
                      setAlertActionBusyId(alert.id);
                      setAlertsError(null);
                      try {
                        const updated = action === "ack"
                          ? await acknowledgeAnalyticsAlert(alert.id)
                          : await resolveAnalyticsAlert(alert.id);

                        setAlerts((current) => {
                          // If we are filtering by status, remove rows that no longer match.
                          if (alertsStatus && updated.status !== alertsStatus) {
                            return current.filter((row) => row.id !== alert.id);
                          }
                          return current.map((row) => (row.id === alert.id ? updated : row));
                        });
                      } catch (err) {
                        console.error("Alert update failed", err);
                        setAlertsError(err instanceof Error ? err.message : "Unable to update alert.");
                      } finally {
                        setAlertActionBusyId((current) => (current === alert.id ? null : current));
                      }
                    }

                    return (
                      <div key={alert.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${severityBadgeClass(alert.severity)}`}>
                              {alert.severity}
                            </span>
                            {alert.metric_key ? (
                              <span className="text-xs font-medium text-slate-500">{alert.metric_key}</span>
                            ) : null}
                            <span className="text-xs text-slate-500">{alert.baseline_window_days}d</span>
                            {deltaLabel ? (
                              <span className="text-xs font-semibold text-slate-700">{deltaLabel}</span>
                            ) : null}
                          </div>

                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              onClick={() => injectAlertContext(alert)}
                            >
                              Open
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!canAck || actionsDisabled}
                              onClick={() => void updateAlert("ack")}
                            >
                              Acknowledge
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!canResolve || actionsDisabled}
                              onClick={() => void updateAlert("resolve")}
                            >
                              Resolve
                            </Button>
                          </div>
                        </div>

                        <p className="mt-2 text-sm font-semibold text-slate-900">{alert.title}</p>
                        <p className="mt-1 line-clamp-2 text-sm text-slate-600">{alert.summary}</p>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                  No alerts for the selected filters.
                </div>
              )
            ) : null}
          </section>

          {messages.length === 0 ? (
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Ask a question about this report. EI will use governed metrics from the analytics layer.
            </div>
          ) : null}

          <div className="mt-4 space-y-4">
            {messages.map((msg) => {
              const isUser = msg.role === "user";
              if (isUser) {
                return (
                  <div key={msg.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white">
                      {msg.content}
                    </div>
                  </div>
                );
              }

              const statusTone = msg.status === "error" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-slate-200 bg-white text-slate-800";

              return (
                <div key={msg.id} className="flex justify-start">
                  <div className={`max-w-[90%] rounded-2xl border px-4 py-3 text-sm shadow-sm ${statusTone}`}>
                    <div className="whitespace-pre-line">{msg.status === "loading" ? "Analyzing metrics..." : msg.content}</div>
                    {msg.status === "loading" ? (
                      <div className="mt-2 inline-flex items-center gap-2 text-xs text-slate-500">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Working...
                      </div>
                    ) : null}

                    {msg.status !== "loading" ? (
                      <div className="mt-3 space-y-2">
                        <div className="text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Metric keys:</span>{" "}
                          {msg.metricKeysUsed.length > 0 ? msg.metricKeysUsed.join(", ") : "none"}
                        </div>
                        <div className="text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Filters:</span>{" "}
                          {msg.filters ? `${msg.filters.start} to ${msg.filters.end}` : "none"}
                        </div>
                        <div className="text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Suggested next actions:</span>
                          {msg.suggestedNextActions.length > 0 ? (
                            <ul className="mt-1 list-disc space-y-1 pl-5">
                              {msg.suggestedNextActions.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          ) : (
                            <span> none</span>
                          )}
                        </div>
                      </div>
                    ) : null}

                    {msg.status === "error" ? (
                      <div className="mt-3">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const lastUser = [...messages].reverse().find((m) => m.role === "user");
                            if (lastUser) {
                              void sendMessage(lastUser.content);
                            }
                          }}
                        >
                          Retry
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <form
          className="border-t border-slate-200 px-5 py-4"
          onSubmit={(event) => {
            event.preventDefault();
            void sendMessage(draft);
          }}
        >
          <div className="flex items-center gap-2">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about KPIs, trends, or risk signals..."
              className="h-10 flex-1 rounded-lg border border-slate-200 px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
            <Button type="submit" disabled={isSending || !draft.trim()} className="h-10 gap-2">
              <Send className="h-4 w-4" />
              Send
            </Button>
          </div>
        </form>
      </aside>
    </>
  );
}

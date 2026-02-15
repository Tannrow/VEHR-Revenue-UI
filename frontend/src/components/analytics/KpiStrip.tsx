"use client";

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { defaultKpisForReport } from "@/lib/analytics/catalog";
import { queryAnalyticsMetric, type AnalyticsQueryResponse, type AnalyticsQueryRow } from "@/lib/analytics/api";

type KpiStripProps = {
  reportKey: string;
  metricKeys?: string[];
};

type KpiCardModel = {
  metricKey: string;
  label: string;
  currentValue: number | null;
  previousValue: number | null;
  deltaPct: number | null;
  series: Array<{ x: string; y: number }>;
  error?: string;
};

function formatDateYmd(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfWeekMonday(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  // JS getDay(): 0=Sunday ... 6=Saturday. Convert to Monday-based offset.
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

function isRateMetric(metricKey: string): boolean {
  const key = metricKey.toLowerCase();
  return key.includes("rate");
}

function isCurrencyMetric(metricKey: string): boolean {
  const key = metricKey.toLowerCase();
  return key.includes("charge") || key.includes("paid") || key.startsWith("ar_") || key.includes("ar_balance");
}

function formatMetricValue(metricKey: string, value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }

  if (isRateMetric(metricKey)) {
    const ratio = value <= 1 ? value * 100 : value;
    return `${ratio.toFixed(1)}%`;
  }

  if (isCurrencyMetric(metricKey)) {
    return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  }

  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function titleCaseFromKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function MiniSparkline({ points }: { points: Array<{ x: string; y: number }> }) {
  if (points.length < 2) {
    return <div className="h-5 w-full" />;
  }

  const width = 120;
  const height = 24;
  const values = points.map((p) => p.y);
  const minY = Math.min(...values);
  const maxY = Math.max(...values);
  const span = maxY - minY || 1;

  const path = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * (width - 4) + 2;
      const y = height - (((point.y - minY) / span) * (height - 6) + 3);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-5 w-full">
      <path d={path} fill="none" stroke="rgb(99 102 241)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function splitWeeklyWindows(now: Date) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const weekStart = startOfWeekMonday(today);
  const currentEnd = today;
  const windowDays = Math.max(1, Math.round((currentEnd.getTime() - weekStart.getTime()) / 86400000) + 1);

  const previousStart = addDays(weekStart, -7);
  const previousEnd = addDays(previousStart, windowDays - 1);

  return {
    current: { start: weekStart, end: currentEnd },
    previous: { start: previousStart, end: previousEnd },
    query: { start: previousStart, end: currentEnd },
  };
}

function numericSeriesFromRows(rows: AnalyticsQueryRow[]): Array<{ x: string; y: number }> {
  const points: Array<{ x: string; y: number }> = [];
  for (const row of rows) {
    if (typeof row.value_num !== "number") {
      continue;
    }
    if (row.kpi_date) {
      points.push({ x: row.kpi_date, y: row.value_num });
      continue;
    }
    if (row.as_of_ts) {
      points.push({ x: row.as_of_ts, y: row.value_num });
    }
  }
  return points;
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

function aggregateValue(metricKey: string, rows: AnalyticsQueryRow[]): number | null {
  const values = rows
    .map((row) => row.value_num)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
  if (values.length === 0) {
    return null;
  }
  if (isRateMetric(metricKey)) {
    const sum = values.reduce((acc, value) => acc + value, 0);
    return sum / values.length;
  }
  return values.reduce((acc, value) => acc + value, 0);
}

function latestValue(rows: AnalyticsQueryRow[]): number | null {
  const values = rows
    .map((row) => row.value_num)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
  if (values.length === 0) {
    return null;
  }
  return values[values.length - 1];
}

function computeCard(metricKey: string, payload: AnalyticsQueryResponse, now: Date): KpiCardModel {
  const windows = splitWeeklyWindows(now);
  const currentRows = rowsInWindow(payload.rows, windows.current.start, windows.current.end);
  const previousRows = rowsInWindow(payload.rows, windows.previous.start, windows.previous.end);

  const isSnapshot = payload.grain === "snapshot";
  const currentValue = isSnapshot ? latestValue(currentRows) : aggregateValue(metricKey, currentRows);
  const previousValue = isSnapshot ? latestValue(previousRows) : aggregateValue(metricKey, previousRows);

  let deltaPct: number | null = null;
  if (previousValue !== null && previousValue !== 0 && currentValue !== null) {
    deltaPct = (currentValue - previousValue) / Math.abs(previousValue);
  }

  const series = numericSeriesFromRows(payload.rows);
  const label = titleCaseFromKey(metricKey);

  return {
    metricKey,
    label,
    currentValue,
    previousValue,
    deltaPct,
    series,
  };
}

export default function KpiStrip({ reportKey, metricKeys }: KpiStripProps) {
  const keys = useMemo(() => {
    const resolved = metricKeys && metricKeys.length > 0 ? metricKeys : defaultKpisForReport(reportKey);
    return resolved.filter(Boolean).slice(0, 6);
  }, [metricKeys, reportKey]);

  const [cards, setCards] = useState<KpiCardModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const now = new Date();
    const windows = splitWeeklyWindows(now);
    const start = formatDateYmd(windows.query.start);
    const end = formatDateYmd(windows.query.end);

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const results = await Promise.all(
          keys.map(async (metricKey) => {
            try {
              const payload = await queryAnalyticsMetric(metricKey, { start, end });
              return computeCard(metricKey, payload, now);
            } catch (metricError) {
              const message = metricError instanceof Error ? metricError.message : "Unable to load metric.";
              return {
                metricKey,
                label: titleCaseFromKey(metricKey),
                currentValue: null,
                previousValue: null,
                deltaPct: null,
                series: [],
                error: message,
              } satisfies KpiCardModel;
            }
          }),
        );

        if (!isMounted) return;
        setCards(results);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Unable to load KPI summary.");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      isMounted = false;
    };
  }, [keys]);

  if (isLoading) {
    return (
      <div className="sticky top-0 z-10 -mx-6 mb-6 border-b border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
        <div className="flex gap-3 overflow-x-auto pb-1">
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={`kpi-loading-${index}`}
              className="min-w-[220px] flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
            >
              <div className="h-3 w-28 animate-pulse rounded bg-slate-100" />
              <div className="mt-2 h-6 w-24 animate-pulse rounded bg-slate-100" />
              <div className="mt-2 h-5 w-full animate-pulse rounded bg-slate-100" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sticky top-0 z-10 -mx-6 mb-6 border-b border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          KPI summary unavailable: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="sticky top-0 z-10 -mx-6 mb-6 border-b border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
      <div className="flex items-stretch gap-3 overflow-x-auto pb-1">
        {cards.map((card) => {
          const delta = card.deltaPct;
          const deltaLabel = delta === null ? "No prior period" : `${Math.abs(delta * 100).toFixed(1)}%`;
          const isPositive = delta !== null && delta > 0;
          const DeltaIcon = delta === null ? Minus : isPositive ? ArrowUpRight : ArrowDownRight;
          const deltaColor = delta === null ? "text-slate-500" : isPositive ? "text-emerald-600" : "text-rose-600";

          return (
            <div
              key={card.metricKey}
              className="min-w-[240px] flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{card.label}</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {formatMetricValue(card.metricKey, card.currentValue)}
                  </p>
                </div>

                <div className={`inline-flex items-center gap-1 text-xs font-semibold ${deltaColor}`}>
                  <DeltaIcon className="h-4 w-4" />
                  <span>{deltaLabel}</span>
                </div>
              </div>

              <div className="mt-2">
                {card.error ? (
                  <p className="text-xs text-rose-600">{card.error}</p>
                ) : (
                  <MiniSparkline points={card.series.slice(-14)} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

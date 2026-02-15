"use client";

import { useEffect, useMemo, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";

type TrendPoint = {
  x: string;
  y: number | null;
};

type TrendSeries = {
  metric_key: string;
  label: string;
  points: TrendPoint[];
};

type KpiCard = {
  metric_key: string;
  label: string;
  category: string;
  value_num: number | null;
  point_count: number;
};

type GeneratedReportPayload = {
  report_id: string;
  report_key: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  content_json: {
    title?: string;
    sections?: {
      kpis?: KpiCard[];
      trends?: TrendSeries[];
      anomalies?: string[];
      recommended_actions?: string[];
    };
  };
};

type GeneratedReportViewProps = {
  reportId: string;
};

function formatMetricValue(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function MiniLineChart({ points }: { points: TrendPoint[] }) {
  const numericPoints = points.filter((point) => typeof point.y === "number") as Array<{ x: string; y: number }>;
  if (numericPoints.length === 0) {
    return <div className="text-xs text-[var(--neutral-muted)]">No trend points available.</div>;
  }
  if (numericPoints.length === 1) {
    return (
      <div className="text-xs text-[var(--neutral-muted)]">
        Single point: {numericPoints[0].x} = {formatMetricValue(numericPoints[0].y)}
      </div>
    );
  }

  const width = 360;
  const height = 120;
  const minY = Math.min(...numericPoints.map((point) => point.y));
  const maxY = Math.max(...numericPoints.map((point) => point.y));
  const ySpan = maxY - minY || 1;

  const path = numericPoints
    .map((point, index) => {
      const x = (index / (numericPoints.length - 1)) * (width - 16) + 8;
      const y = height - (((point.y - minY) / ySpan) * (height - 20) + 10);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full rounded-[var(--radius-6)] bg-[var(--surface-muted)]">
      <path d={path} fill="none" stroke="var(--brand-primary)" strokeWidth="2" />
    </svg>
  );
}

export default function GeneratedReportView({ reportId }: GeneratedReportViewProps) {
  const [report, setReport] = useState<GeneratedReportPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    async function loadReport() {
      try {
        const response = await apiFetch<GeneratedReportPayload>(
          `/api/v1/reports/generated/${encodeURIComponent(reportId)}`,
          { cache: "no-store" },
        );
        if (!isMounted) {
          return;
        }
        setReport(response);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load generated report.");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadReport();
    return () => {
      isMounted = false;
    };
  }, [reportId]);

  const kpis = useMemo(() => report?.content_json.sections?.kpis ?? [], [report]);
  const trends = useMemo(() => report?.content_json.sections?.trends ?? [], [report]);
  const anomalies = useMemo(() => report?.content_json.sections?.anomalies ?? [], [report]);
  const recommendedActions = useMemo(() => report?.content_json.sections?.recommended_actions ?? [], [report]);

  if (isLoading) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <div className="h-6 w-52 animate-pulse rounded bg-[var(--surface-muted)]" />
        <div className="mt-[var(--space-10)] h-40 w-full animate-pulse rounded bg-[var(--surface-muted)]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-12)] py-[var(--space-10)] text-sm text-[var(--status-critical)]">
        {error}
      </div>
    );
  }

  if (!report) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-12)] py-[var(--space-10)] text-sm text-[var(--neutral-muted)]">
        No report data found.
      </div>
    );
  }

  return (
    <div className="space-y-[var(--space-16)]" data-testid="generated-report-view">
      <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
        <CardHeader>
          <CardTitle className="text-lg text-[var(--neutral-text)]">
            {report.content_json.title ?? "Weekly Executive Overview"}
          </CardTitle>
          <CardDescription className="text-sm text-[var(--neutral-muted)]">
            {report.period_start} to {report.period_end} - Generated {new Date(report.generated_at).toLocaleString()}
          </CardDescription>
        </CardHeader>
      </Card>

      <section className="grid gap-[var(--space-12)] md:grid-cols-3" data-testid="generated-report-kpis">
        {kpis.length > 0 ? (
          kpis.map((kpi) => (
            <Card key={kpi.metric_key} className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
              <CardHeader className="pb-[var(--space-8)]">
                <CardDescription className="text-xs uppercase tracking-[0.08em] text-[var(--neutral-muted)]">
                  {kpi.category}
                </CardDescription>
                <CardTitle className="text-sm text-[var(--neutral-text)]">{kpi.label}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold text-[var(--neutral-text)]">{formatMetricValue(kpi.value_num)}</div>
                <div className="mt-[var(--space-6)] text-xs text-[var(--neutral-muted)]">{kpi.point_count} source points</div>
              </CardContent>
            </Card>
          ))
        ) : (
          <Card className="md:col-span-3">
            <CardContent className="pt-[var(--space-12)] text-sm text-[var(--neutral-muted)]">
              No KPI cards were generated from current data.
            </CardContent>
          </Card>
        )}
      </section>

      <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
        <CardHeader>
          <CardTitle className="text-base text-[var(--neutral-text)]">Trends</CardTitle>
          <CardDescription>Series built from governed KPI records.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-[var(--space-12)]">
          {trends.length > 0 ? (
            trends.map((series) => (
              <div key={series.metric_key} className="space-y-[var(--space-8)] rounded-[var(--radius-6)] border border-[var(--border)] p-[var(--space-10)]">
                <div className="text-sm font-medium text-[var(--neutral-text)]">{series.label}</div>
                <MiniLineChart points={series.points} />
              </div>
            ))
          ) : (
            <div className="text-sm text-[var(--neutral-muted)]">No trend series available for this period.</div>
          )}
        </CardContent>
      </Card>

      <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
        <CardHeader>
          <CardTitle className="text-base text-[var(--neutral-text)]">Trend Data</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Points</TableHead>
                <TableHead>First Point</TableHead>
                <TableHead>Last Point</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trends.map((series) => (
                <TableRow key={`trend-row-${series.metric_key}`}>
                  <TableCell>{series.label}</TableCell>
                  <TableCell>{series.points.length}</TableCell>
                  <TableCell>{series.points[0]?.x ?? "-"}</TableCell>
                  <TableCell>{series.points[series.points.length - 1]?.x ?? "-"}</TableCell>
                </TableRow>
              ))}
              {trends.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-sm text-[var(--neutral-muted)]">
                    No trend rows available.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-[var(--space-12)] md:grid-cols-2">
        <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
          <CardHeader>
            <CardTitle className="text-base text-[var(--neutral-text)]">Anomalies</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--neutral-muted)]">
            {anomalies.length > 0 ? (
              <ul className="list-disc pl-5">
                {anomalies.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              "No anomalies captured yet."
            )}
          </CardContent>
        </Card>

        <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
          <CardHeader>
            <CardTitle className="text-base text-[var(--neutral-text)]">Recommended Actions</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--neutral-muted)]">
            {recommendedActions.length > 0 ? (
              <ul className="list-disc pl-5">
                {recommendedActions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              "No recommended actions yet."
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

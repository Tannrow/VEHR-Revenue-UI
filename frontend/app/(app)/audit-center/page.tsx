"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import MetricCard from "../_components/MetricCard";
import ClinicalAuditsPanel from "./ClinicalAuditsPanel";

type Aggregate = {
  key: string;
  count: number;
};

type SummaryResponse = {
  window_hours: number;
  total_events: number;
  by_action: Aggregate[];
  by_entity_type: Aggregate[];
  top_actors: Aggregate[];
  hourly_activity: { hour_start: string; count: number }[];
};

type Anomaly = {
  kind: string;
  severity: string;
  description: string;
  event_ids: string[];
  related_actor?: string | null;
  sample_time: string;
};

type AssistantBrief = {
  window_hours: number;
  generated_at: string;
  summary: string;
  highlights: string[];
  risk_score: number;
};

function severityBadge(severity: string) {
  if (severity === "high") {
    return "destructive" as const;
  }
  if (severity === "medium") {
    return "secondary" as const;
  }
  return "outline" as const;
}

export default function AuditCenterPage() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [brief, setBrief] = useState<AssistantBrief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setError(null);
        const [summaryRes, anomalyRes, briefRes] = await Promise.all([
          apiFetch<SummaryResponse>("/api/v1/audit/summary?hours=72", { cache: "no-store" }),
          apiFetch<Anomaly[]>("/api/v1/audit/anomalies?hours=72&limit=10", { cache: "no-store" }),
          apiFetch<AssistantBrief>("/api/v1/audit/assistant/brief?hours=72", { cache: "no-store" }),
        ]);
        if (!isMounted) return;
        setSummary(summaryRes);
        setAnomalies(anomalyRes);
        setBrief(briefRes);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to load audit center data");
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const riskScore = brief?.risk_score ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          Compliance
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Audit Center</h1>
        <p className="text-sm text-slate-500">
          Continuous monitoring, anomaly detection, and AI-assisted compliance briefings.
        </p>
      </div>

      {error ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Window"
          value={`${summary?.window_hours ?? 72}h`}
          hint="Analysis interval"
        />
        <MetricCard
          label="Total Events"
          value={`${summary?.total_events ?? 0}`}
          hint="Captured audit entries"
        />
        <MetricCard
          label="Risk Score"
          value={`${riskScore}/100`}
          hint="Rule-assisted risk index"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
            <CardTitle className="text-base text-slate-900">Assistant Brief</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            <p className="text-sm text-slate-700">
              {brief?.summary ?? "Assistant brief not available yet."}
            </p>
            <div className="space-y-2">
              {(brief?.highlights ?? []).map((item) => (
                <div
                  key={item}
                  className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs text-slate-600"
                >
                  {item}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200/70 shadow-sm">
          <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
            <CardTitle className="text-base text-slate-900">Top Signals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Frequent Actions
              </p>
              <div className="mt-2 space-y-2">
                {(summary?.by_action ?? []).slice(0, 4).map((item) => (
                  <div key={item.key} className="flex items-center justify-between text-sm text-slate-700">
                    <span>{item.key}</span>
                    <span className="font-mono text-xs text-slate-500">{item.count}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Active Actors
              </p>
              <div className="mt-2 space-y-2">
                {(summary?.top_actors ?? []).slice(0, 4).map((item) => (
                  <div key={item.key} className="flex items-center justify-between text-sm text-slate-700">
                    <span className="truncate">{item.key}</span>
                    <span className="font-mono text-xs text-slate-500">{item.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border-slate-200/70 shadow-sm">
        <CardHeader className="border-b border-slate-200/70 bg-slate-50/70">
          <CardTitle className="text-base text-slate-900">Anomaly Queue</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-5">
          {anomalies.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
              No anomalies in this window.
            </div>
          ) : (
            anomalies.map((item) => (
              <div
                key={`${item.kind}-${item.sample_time}-${item.description}`}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900">{item.kind}</div>
                  <Badge variant={severityBadge(item.severity)}>{item.severity}</Badge>
                </div>
                <p className="mt-2 text-sm text-slate-600">{item.description}</p>
                <p className="mt-2 text-xs text-slate-500">
                  {new Date(item.sample_time).toLocaleString()} | Events: {item.event_ids.length}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <ClinicalAuditsPanel />
    </div>
  );
}

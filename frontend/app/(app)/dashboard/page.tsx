"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";
import { apiFetch } from "@/lib/api";

type SummaryResponse = {
  total_events: number;
  by_action: { key: string; count: number }[];
  by_entity_type: { key: string; count: number }[];
};

type UsageInsights = {
  template_count: number;
  submission_count: number;
};

type ConnectorCatalog = {
  total: number;
};

export default function DashboardPage() {
  const [auditSummary, setAuditSummary] = useState<SummaryResponse | null>(null);
  const [formUsage, setFormUsage] = useState<UsageInsights | null>(null);
  const [connectors, setConnectors] = useState<ConnectorCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setError(null);
        const [auditRes, formsRes, integrationsRes] = await Promise.all([
          apiFetch<SummaryResponse>("/api/v1/audit/summary?hours=24", { cache: "no-store" }),
          apiFetch<UsageInsights>("/api/v1/forms/templates/insights/usage", { cache: "no-store" }),
          apiFetch<ConnectorCatalog>("/api/v1/integrations/connectors", { cache: "no-store" }),
        ]);
        if (!isMounted) return;
        setAuditSummary(auditRes);
        setFormUsage(formsRes);
        setConnectors(integrationsRes);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to load dashboard metrics");
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          Operations
        </p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Executive Dashboard</h1>
        <p className="text-sm text-slate-500">
          Clinical workload, compliance signals, and integration readiness in one control plane.
        </p>
      </div>

      {error ? (
        <Card className="border-rose-200 bg-rose-50/80">
          <CardContent className="pt-6 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Audit Events (24h)"
          value={`${auditSummary?.total_events ?? 0}`}
          hint="Captured compliance entries"
        />
        <MetricCard
          label="Form Submissions"
          value={`${formUsage?.submission_count ?? 0}`}
          hint={`${formUsage?.template_count ?? 0} templates in library`}
        />
        <MetricCard
          label="Connector Footprint"
          value={`${connectors?.total ?? 0}`}
          hint="Integration adapters available"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card className="border-slate-200/80 bg-white">
          <CardHeader className="border-b border-slate-100">
            <CardTitle className="text-base text-slate-900">Action Velocity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 pt-4">
            {(auditSummary?.by_action ?? []).slice(0, 6).map((item) => (
              <div
                key={item.key}
                className="flex items-center justify-between border-b border-slate-100 px-1 py-2 text-sm last:border-b-0"
              >
                <span className="text-slate-700">{item.key}</span>
                <span className="font-mono text-xs text-slate-500">{item.count}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border-slate-200/80 bg-white">
          <CardHeader className="border-b border-slate-100">
            <CardTitle className="text-base text-slate-900">Entity Coverage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 pt-4">
            {(auditSummary?.by_entity_type ?? []).slice(0, 6).map((item) => (
              <div key={item.key} className="border-b border-slate-100 px-1 py-2 last:border-b-0">
                <div className="text-sm font-semibold text-slate-800">{item.key}</div>
                <div className="text-xs text-slate-500">{item.count} events</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type SummaryResponse = {
  window_hours: number;
  total_events: number;
  by_action: { key: string; count: number }[];
};

export default function ReportsPage() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadSummary() {
      try {
        const data = await apiFetch<SummaryResponse>("/api/v1/audit/summary?hours=72", { cache: "no-store" });
        if (!isMounted) return;
        setSummary(data);
      } catch (loadError) {
        if (!isMounted) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load reports.");
      }
    }

    void loadSummary();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Encompass 360</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Reports</h1>
        <p className="text-sm text-slate-500">Operational summaries and activity snapshots.</p>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-900">Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0 text-sm text-slate-600">
            <p>Window: {summary?.window_hours ?? 72} hours</p>
            <p>Total tracked events: {summary?.total_events ?? 0}</p>
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-900">Top Activity Types</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {(summary?.by_action ?? []).slice(0, 6).map((entry) => (
              <div key={entry.key} className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-sm text-slate-700">{entry.key}</p>
                <p className="text-xs text-slate-500">{entry.count} events</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

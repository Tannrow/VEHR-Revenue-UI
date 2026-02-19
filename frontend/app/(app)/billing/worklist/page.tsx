"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Filter, Loader2, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchFinanceInsight, normalizeFinanceAIEnvelope, type FinanceAIEnvelope } from "@/lib/finance-ai";

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base text-slate-900">{title}</CardTitle>
        <Badge variant="outline">AI advisory</Badge>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-slate-800">{children}</CardContent>
    </Card>
  );
}

export default function WorklistPage() {
  const [payload, setPayload] = useState<FinanceAIEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const advisory = payload?.advisory;
  const tierBadges = useMemo(() => {
    if (!advisory?.recommended_actions) return [];
    return advisory.recommended_actions.map((item, idx) => (
      <Badge key={`${item.action}-${idx}`} variant="secondary" className="capitalize">
        {item.urgency} priority • {item.impact_estimate}
      </Badge>
    ));
  }, [advisory?.recommended_actions]);

  async function loadInsights() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFinanceInsight("/api/v1/ai/worklist", {
        scope: "revenue_worklist",
        include_drafts: true,
      });
      setPayload(normalizeFinanceAIEnvelope(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load worklist intelligence");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadInsights();
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-slate-500">Revenue</p>
          <h1 className="text-[1.8rem] font-semibold tracking-tight text-slate-900">Worklist</h1>
          <p className="text-sm text-slate-600">Prioritized queue with recommended actions and drafts.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadInsights} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
          <Button variant="default" size="sm">
            <CheckCircle2 className="mr-2 h-4 w-4" />
            Mark reviewed
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[color-mix(in_srgb,var(--neutral-border)_80%,white)] bg-white px-3 py-2">
        <Badge variant="secondary" className="gap-2">
          <Filter className="h-4 w-4" />
          Filters (placeholder)
        </Badge>
        <Badge variant="outline">High dollar</Badge>
        <Badge variant="outline">Aged &gt; 15d</Badge>
        <Badge variant="outline">Auth/Coding</Badge>
      </div>

      {loading ? (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading worklist intelligence…
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard title="Prioritized Narrative">
          <p>{advisory?.summary ?? "No narrative available yet."}</p>
          <div className="flex flex-wrap gap-2">{tierBadges}</div>
        </SectionCard>

        <SectionCard title="Root Cause">
          <p>{advisory?.root_cause ?? "Root cause not available."}</p>
          <p className="text-xs text-slate-500">AI is advisory only; verify before action.</p>
        </SectionCard>

        <SectionCard title="Recommended Actions">
          <div className="space-y-2">
            {advisory?.recommended_actions?.length ? (
              advisory.recommended_actions.map((item, idx) => (
                <div
                  key={`${item.action}-${idx}`}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">{item.action}</p>
                    <Badge variant="outline" className="capitalize">
                      {item.urgency}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-600">Impact {item.impact_estimate}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">No actions provided.</p>
            )}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Drafts">
        <div className="space-y-2">
          {advisory?.drafts?.length ? (
            advisory.drafts.map((draft, idx) => (
              <div key={`${draft.type}-${idx}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{draft.type}</p>
                <p className="text-sm text-slate-800">{draft.content}</p>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-600">No drafts generated.</p>
          )}
        </div>
      </SectionCard>
    </div>
  );
}


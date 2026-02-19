"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, FileText, Loader2, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchFinanceInsight, normalizeFinanceAIEnvelope, type FinanceAIEnvelope } from "@/lib/finance-ai";

export default function ExecutiveSummaryPage() {
  const [payload, setPayload] = useState<FinanceAIEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const advisory = payload?.advisory;

  async function loadIntel() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFinanceInsight("/api/v1/ai/executive-summary", { scope: "executive" });
      setPayload(normalizeFinanceAIEnvelope(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load executive summary");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadIntel();
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-slate-500">Revenue</p>
          <h1 className="text-[1.8rem] font-semibold tracking-tight text-slate-900">Executive Summary</h1>
          <p className="text-sm text-slate-600">Headline summary, exposure, drivers, and actions ready for CFO review.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadIntel} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
          <Badge variant="secondary" className="gap-2">
            <FileText className="h-4 w-4" />
            CFO-ready
          </Badge>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading executive summary…
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-slate-900">Headline Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-800">
            <p>{advisory?.summary ?? "No headline available."}</p>
            <Badge variant="outline">AI advisory only</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-slate-900">Financial Exposure</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-800">
            <p>{advisory?.root_cause ?? "No exposure details available."}</p>
            <div className="space-y-1 text-xs text-slate-600">
              {advisory?.questions_needed?.map((item, idx) => (
                <p key={`${item}-${idx}`}>• {item}</p>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base text-slate-900">Key Drivers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-800">
          <div className="space-y-2">
            {advisory?.assumptions?.length ? (
              advisory.assumptions.map((item, idx) => (
                <div key={`${item}-${idx}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-sm text-slate-800">{item}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">No drivers listed.</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base text-slate-900">Actions</CardTitle>
          <Badge variant="outline">AI advisory</Badge>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-800">
          {advisory?.recommended_actions?.length ? (
            advisory.recommended_actions.map((item, idx) => (
              <div key={`${item.action}-${idx}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
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
            <p className="text-sm text-slate-600">No actions available.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base text-slate-900">Questions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-800">
          <ul className="list-disc space-y-1 pl-4">
            {advisory?.questions_needed?.length ? (
              advisory.questions_needed.map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)
            ) : (
              <li>No open questions.</li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}


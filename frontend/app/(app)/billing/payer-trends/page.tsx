"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, Loader2, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchFinanceInsight, normalizeFinanceAIEnvelope, type FinanceAIEnvelope } from "@/lib/finance-ai";

export default function PayerTrendsPage() {
  const [payload, setPayload] = useState<FinanceAIEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const advisory = payload?.advisory;

  async function loadIntel() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFinanceInsight("/api/v1/ai/payer-intel", {
        scope: "payer_intel",
      });
      setPayload(normalizeFinanceAIEnvelope(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load payer intelligence");
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
          <h1 className="text-[1.8rem] font-semibold tracking-tight text-slate-900">Payer Trends</h1>
          <p className="text-sm text-slate-600">Trend summary, revenue leaks, and operational adjustments.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadIntel} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
          <Badge variant="secondary" className="gap-2">
            <BarChart3 className="h-4 w-4" />
            Advisory
          </Badge>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading payer intelligence…
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-slate-900">Trend Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-800">
            <p>{advisory?.summary ?? "No trend summary available."}</p>
            <Badge variant="outline">AI advisory</Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-slate-900">Revenue Leaks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-800">
            <p>{advisory?.root_cause ?? "No leak analysis available."}</p>
            <div className="space-y-1">
              {advisory?.questions_needed?.map((item, idx) => (
                <p key={`${item}-${idx}`} className="text-xs text-slate-600">
                  • {item}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-slate-900">Operational Adjustments</CardTitle>
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
              <p className="text-sm text-slate-600">No adjustments available.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


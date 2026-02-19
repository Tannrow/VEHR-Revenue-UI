"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, Loader2, RefreshCcw, ShieldCheck, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type AggressivePayer,
  type RevenueCommandSnapshot,
  fetchLatestRevenueSnapshot,
} from "@/lib/revenue-command";

function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "$0";
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) return "$0";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(numeric);
}

function formatDate(value: string | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function AggressivePayerRow({ payer }: { payer: AggressivePayer }) {
  return (
    <div className="flex items-start justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div>
        <p className="text-sm font-semibold text-slate-900">{payer.payer}</p>
        <p className="text-xs text-slate-600">{payer.aggression_drivers?.join(", ") || "No drivers listed"}</p>
      </div>
      <Badge variant="outline" className="text-xs">
        {payer.aggression_tier} · {payer.aggression_score}
      </Badge>
    </div>
  );
}

export default function RevenueCommandPage() {
  const [snapshot, setSnapshot] = useState<RevenueCommandSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const aggressionAlertCount = snapshot?.aggression_change_alerts?.length ?? 0;

  async function loadSnapshot() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLatestRevenueSnapshot();
      setSnapshot(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load revenue command snapshot");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSnapshot();
  }, []);

  const worklistSummary = useMemo(() => snapshot?.worklist_priority_summary ?? {}, [snapshot]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-slate-500">Revenue Command</p>
          <h1 className="text-[1.9rem] font-semibold tracking-tight text-slate-900">Daily Command Snapshot</h1>
          <p className="text-sm text-slate-600">
            Deterministic daily snapshot across exposure, aggression, and execution priorities.
          </p>
          <p className="text-xs text-slate-500">Generated at {formatDate(snapshot?.generated_at)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadSnapshot} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
          <Badge variant="secondary" className="gap-2">
            <ShieldCheck className="h-4 w-4" />
            Deterministic
          </Badge>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-3">
        <Card className="bg-gradient-to-br from-slate-50 to-white">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">Total Exposure</CardTitle>
          </CardHeader>
          <CardContent className="flex items-end justify-between">
            <p className="text-2xl font-semibold text-slate-900">{formatMoney(snapshot?.total_exposure)}</p>
            <Badge variant="outline">30d recovery {_formatShort(snapshot?.expected_recovery_30_day)}</Badge>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-slate-50 to-white">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">Expected Recovery (30d)</CardTitle>
          </CardHeader>
          <CardContent className="flex items-end justify-between">
            <p className="text-2xl font-semibold text-emerald-700">{formatMoney(snapshot?.expected_recovery_30_day)}</p>
            <Badge variant="outline">Short-term {_formatShort(snapshot?.short_term_cash_opportunity)}</Badge>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-slate-50 to-white">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">Short-Term Cash Opportunity</CardTitle>
          </CardHeader>
          <CardContent className="flex items-end justify-between">
            <p className="text-2xl font-semibold text-blue-700">{formatMoney(snapshot?.short_term_cash_opportunity)}</p>
            <Badge variant="outline">Alerts {aggressionAlertCount}</Badge>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">High-Risk Claims</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-2xl font-semibold text-slate-900">{snapshot?.high_risk_claim_count ?? 0}</p>
            <p className="text-xs text-slate-600">Aging &gt; 90d, denials, or &gt;10% variance.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">Critical Pre-Submission Gaps</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-2xl font-semibold text-slate-900">
              {snapshot?.critical_pre_submission_count ?? 0}
            </p>
            <p className="text-xs text-slate-600">Claims without ledgers or pending service validations.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-700">Aggression Alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-2xl font-semibold text-slate-900">{aggressionAlertCount}</p>
            <p className="text-xs text-slate-600">Change detection across payer aggression and exposure shifts.</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex items-center justify-between pb-2">
            <CardTitle className="text-sm font-semibold text-slate-900">Top Aggressive Payers</CardTitle>
            <Badge variant="outline">Aggression v{snapshot?.scoring_versions.aggression_version}</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {snapshot?.top_aggressive_payers?.length ? (
              snapshot.top_aggressive_payers.map((payer) => <AggressivePayerRow key={payer.payer} payer={payer} />)
            ) : (
              <p className="text-sm text-slate-600">No aggressive payers detected.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex items-center justify-between pb-2">
            <CardTitle className="text-sm font-semibold text-slate-900">Worklist Priority</CardTitle>
            <Badge variant="outline">Risk v{snapshot?.scoring_versions.risk_version}</Badge>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-3">
            {["high", "medium", "low"].map((bucket) => (
              <div key={bucket} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <p className="text-xs uppercase text-slate-500">{bucket}</p>
                <p className="text-xl font-semibold text-slate-900">{worklistSummary?.[bucket] ?? 0}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex items-center justify-between pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Workflow className="h-4 w-4" />
              30-Day Execution Plan
            </CardTitle>
            <Badge variant="outline">Deterministic</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {snapshot?.execution_plan_30_day?.length ? (
              snapshot.execution_plan_30_day.map((item, idx) => (
                <div key={`${item.title}-${idx}`} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">{(item as { title?: string }).title ?? "Initiative"}</p>
                    <Badge variant="outline">{(item as { priority?: string }).priority ?? "focus"}</Badge>
                  </div>
                  <p className="text-xs text-slate-600">
                    Impact {(item as { expected_impact?: string }).expected_impact ?? "n/a"} ·{" "}
                    {(item as { owner?: string }).owner ?? "Owner TBD"}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">No execution steps defined.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex items-center justify-between pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ArrowUpRight className="h-4 w-4" />
              90-Day Structural Moves
            </CardTitle>
            <Badge variant="outline">Pre-sub v{snapshot?.scoring_versions.pre_submission_version}</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {snapshot?.structural_moves_90_day?.length ? (
              snapshot.structural_moves_90_day.map((item) => (
                <div key={item} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
                  {item}
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-600">No structural moves captured yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function _formatShort(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "$0";
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) return "$0";
  if (numeric >= 1_000_000) {
    return `${(numeric / 1_000_000).toFixed(1)}M`;
  }
  if (numeric >= 1_000) {
    return `${(numeric / 1_000).toFixed(1)}k`;
  }
  return numeric.toFixed(0);
}

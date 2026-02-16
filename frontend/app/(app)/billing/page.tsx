"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";

const billingItems = [
  { item: "Claims pending", status: "Review needed", risk: "Medium" },
  { item: "Remittance exceptions", status: "Attention required", risk: "High" },
  { item: "Submission queue", status: "On track", risk: "Low" },
];

const auditTrail = [
  "Export run initiated for current cycle",
  "Manual adjustment logged by billing supervisor",
  "Exception queue reconciled for prior period",
];

export default function BillingPage() {
  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Oversight</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Billing</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Status-first billing visibility for leadership and operations.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Claims pending" value="24" hint="Awaiting review" />
        <MetricCard label="Exceptions" value="5" hint="Escalate today" />
        <MetricCard label="Export status" value="In progress" hint="Current pay cycle" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">ERA Import</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-slate-600">
            Upload ERA and billed claims PDFs to reconcile in one pass.
            <Button asChild variant="outline">
              <Link href="/billing/era-import">Start import</Link>
            </Button>
          </CardContent>
        </Card>
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Reconciliation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-slate-600">
            Review claim- and line-level reconciliation results.
            <Button asChild variant="outline">
              <Link href="/billing/reconciliation">View results</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Billing status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {billingItems.map((row) => (
              <div key={row.item} className="rounded-lg bg-slate-50 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{row.item}</p>
                  <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${row.risk === "High" ? "ui-status-error" : row.risk === "Medium" ? "ui-status-warning" : "ui-status-success"}`}>
                    {row.risk}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{row.status}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Audit trail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {auditTrail.map((item) => (
              <div key={item} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                {item}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

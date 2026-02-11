"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const funnel = [
  { label: "New prospects", count: 18 },
  { label: "Intake scheduled", count: 9 },
  { label: "Waiting documentation", count: 6 },
  { label: "Ready to onboard", count: 4 },
];

const followUps = [
  { id: "r1", name: "Prospect A", note: "Requested callback after 1 PM", status: "Pending call" },
  { id: "r2", name: "Prospect B", note: "Awaiting insurance card upload", status: "Documentation" },
  { id: "r3", name: "Prospect C", note: "Needs scheduling confirmation", status: "Scheduling" },
];

export default function ReferralsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Encompass 360</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Referrals / Prospects</h1>
        <p className="text-sm text-slate-500">Pipeline visibility for outreach, intake, and conversion.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {funnel.map((item) => (
          <Card key={item.label} className="bg-white shadow-sm">
            <CardHeader className="pb-1">
              <CardTitle className="text-xs uppercase tracking-[0.22em] text-slate-500">{item.label}</CardTitle>
            </CardHeader>
            <CardContent className="pt-1">
              <p className="text-2xl font-semibold text-slate-900">{item.count}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="bg-white shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-slate-900">Prospect Follow-Ups</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          {followUps.map((item) => (
            <div key={item.id} className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-sm font-semibold text-slate-900">{item.name}</p>
              <p className="mt-1 text-xs text-slate-600">{item.note}</p>
              <p className="mt-1 text-xs text-slate-500">{item.status}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

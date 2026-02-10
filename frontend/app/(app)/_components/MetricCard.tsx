import { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
};

export default function MetricCard({ label, value, hint, icon }: MetricCardProps) {
  return (
    <Card className="border-slate-200/80 bg-white">
      <CardHeader className="flex flex-row items-center justify-between pb-1">
        <CardTitle className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          {label}
        </CardTitle>
        {icon ? <span className="text-slate-400">{icon}</span> : null}
      </CardHeader>
      <CardContent className="pt-1">
        <div className="text-2xl font-semibold tracking-tight text-slate-900">{value}</div>
        {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

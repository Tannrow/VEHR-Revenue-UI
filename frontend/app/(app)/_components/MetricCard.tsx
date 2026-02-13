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
    <Card className="border border-[var(--neutral-border)] bg-[var(--neutral-panel)] shadow-[var(--shadow-1)]">
      <CardHeader className="flex flex-row items-center justify-between pb-[var(--space-4)]">
        <CardTitle className="text-[length:var(--font-size-12)] font-semibold uppercase tracking-[0.24em] text-[var(--neutral-muted)]">
          {label}
        </CardTitle>
        {icon ? <span className="text-[var(--neutral-muted)]">{icon}</span> : null}
      </CardHeader>
      <CardContent className="pt-[var(--space-4)]">
        <div className="text-2xl font-semibold tracking-tight text-[var(--neutral-text)]">{value}</div>
        {hint ? <p className="mt-[var(--space-4)] text-[length:var(--font-size-12)] text-[var(--neutral-muted)]">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

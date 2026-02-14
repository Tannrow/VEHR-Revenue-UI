import { ReactNode } from "react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type MetricTone = "neutral" | "info" | "success" | "warn" | "danger";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
  tone?: MetricTone;
  className?: string;
  testId?: string;
};

const toneClass: Record<MetricTone, string> = {
  neutral: "border-[var(--neutral-border)]",
  info: "border-[color-mix(in_srgb,var(--status-informational)_45%,white)]",
  success: "border-[color-mix(in_srgb,var(--status-stable)_45%,white)]",
  warn: "border-[color-mix(in_srgb,var(--status-attention)_45%,white)]",
  danger: "border-[color-mix(in_srgb,var(--status-critical)_45%,white)]",
};

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
  className,
  testId,
}: MetricCardProps) {
  return (
    <Card
      className={cn(
        "bg-[var(--neutral-panel)] shadow-sm transition-shadow duration-150 hover:shadow-md",
        toneClass[tone],
        className,
      )}
      data-testid={testId}
    >
      <CardHeader className="flex flex-row items-center justify-between pb-[var(--space-8)]">
        <p className="ui-type-card-label uppercase tracking-[0.14em] text-[var(--neutral-muted)]">{label}</p>
        {icon ? <span className="text-[var(--neutral-muted)]">{icon}</span> : null}
      </CardHeader>
      <CardContent className="pt-[var(--space-4)]">
        <p className="text-2xl font-semibold tracking-tight text-[var(--neutral-text)]">{value}</p>
        {hint ? <p className="ui-type-meta mt-[var(--space-4)]">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

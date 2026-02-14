import { ReactNode } from "react";

import { MetricCard as BaseMetricCard } from "@/components/enterprise/metric-card";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
  tone?: "neutral" | "info" | "success" | "warn" | "danger";
};

export default function MetricCard({ label, value, hint, icon, tone }: MetricCardProps) {
  return <BaseMetricCard label={label} value={value} hint={hint} icon={icon} tone={tone} />;
}

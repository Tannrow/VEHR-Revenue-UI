"use client";

import { useEffect, useMemo, useState } from "react";

import { DataListRow } from "@/components/enterprise/data-list-row";
import { PageShell } from "@/components/enterprise/page-shell";
import { SectionCard } from "@/components/enterprise/section-card";
import { SidebarNav, type SidebarNavGroup } from "@/components/enterprise/sidebar-nav";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";

import MetricCard from "../_components/MetricCard";

type SummaryResponse = {
  window_hours: number;
  total_events: number;
};

type Anomaly = {
  kind: string;
  severity: string;
  description: string;
  sample_time: string;
};

function toSafeText(value: unknown, fallback = "Unavailable"): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function severityTone(severity: string): "critical" | "attention" | "informational" {
  if (severity === "high") return "critical";
  if (severity === "medium") return "attention";
  return "informational";
}

export default function AuditCenterPage() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [findings, setFindings] = useState<Anomaly[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadData() {
      try {
        setError(null);
        const [summaryRes, anomalyRes] = await Promise.all([
          apiFetch<SummaryResponse>("/api/v1/audit/summary?hours=72", { cache: "no-store" }),
          apiFetch<Anomaly[]>("/api/v1/audit/anomalies?hours=72&limit=8", { cache: "no-store" }),
        ]);
        if (!isMounted) return;
        setSummary(summaryRes);
        setFindings(anomalyRes);
      } catch (loadError) {
        if (!isMounted) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load audit data.");
      }
    }

    void loadData();
    return () => {
      isMounted = false;
    };
  }, []);

  const highRisk = useMemo(
    () => findings.filter((item) => item.severity === "high").length,
    [findings],
  );

  const mediumRisk = useMemo(
    () => findings.filter((item) => item.severity === "medium").length,
    [findings],
  );

  const sidebarGroups = useMemo<SidebarNavGroup[]>(
    () => [
      {
        id: "window",
        label: "Review Window",
        items: [
          {
            id: "last-72h",
            label: "Last 72 Hours",
            description: "Current audit summary period",
            active: true,
            badge: `${summary?.total_events ?? 0} events`,
          },
        ],
      },
      {
        id: "severity",
        label: "Severity Mix",
        items: [
          {
            id: "high",
            label: "High Risk",
            description: "Immediate response required",
            badge: `${highRisk}`,
          },
          {
            id: "medium",
            label: "Medium Risk",
            description: "Track and resolve quickly",
            badge: `${mediumRisk}`,
          },
        ],
      },
    ],
    [highRisk, mediumRisk, summary?.total_events],
  );

  return (
    <PageShell
      eyebrow="Oversight"
      title="Audit Center"
      description="Status-first audit view with clear risk and direct follow-up actions."
      metrics={
        <div className="grid gap-[var(--space-16)] md:grid-cols-3">
          <MetricCard label="Audit window" value={`${summary?.window_hours ?? 72}h`} hint="Current review period" />
          <MetricCard label="Tracked events" value={`${summary?.total_events ?? 0}`} hint="Observed activity" />
          <MetricCard label="High-risk findings" value={`${highRisk}`} hint="Requires immediate review" tone="danger" />
        </div>
      }
      sidebar={<SidebarNav groups={sidebarGroups} testId="audit-sidebar-nav" />}
    >
      {error ? (
        <div className="ui-panel bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-16)] py-[var(--space-12)] ui-type-body text-[var(--status-critical)]">
          {error}
        </div>
      ) : null}

      <SectionCard title="Findings Queue" description="Review anomalies and assign follow-up actions.">
        <div className="space-y-[var(--space-8)]">
          {findings.length === 0 ? (
            <p className="ui-type-body text-[var(--neutral-muted)]">No active findings in this period.</p>
          ) : (
            findings.map((finding) => (
              <DataListRow
                key={`${finding.kind}-${finding.sample_time}`}
                title={toSafeText(finding.kind, "Unknown event")}
                description={toSafeText(finding.description, "No summary available")}
                meta={`Detected: ${new Date(finding.sample_time).toLocaleString()}`}
                statusLabel={toSafeText(finding.severity, "low")}
                statusTone={severityTone(finding.severity)}
                actions={
                  <Button type="button" variant="outline" size="sm">
                    Create follow-up task
                  </Button>
                }
              />
            ))
          )}
        </div>
      </SectionCard>
    </PageShell>
  );
}


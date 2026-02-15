"use client";

import { PowerBIReportEmbed } from "@/components/analytics/powerbi-report-embed";
import { SectionCard } from "@/components/enterprise/section-card";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";

export default function ChartAuditPage() {
  return (
    <div className="flex flex-col gap-[var(--space-24)]" data-testid="chart-audit-page">
      <AppLayoutPageConfig
        moduleLabel="Governance"
        pageTitle="Chart Audit"
        subtitle="Power BI chart audit report scoped to your organization via row-level security."
      />

      <SectionCard
        title="Chart Audit Analytics"
        description="Embedded Power BI report using App-Owns-Data and tenant-scoped identity."
      >
        <PowerBIReportEmbed reportKey="chart_audit" />
      </SectionCard>
    </div>
  );
}

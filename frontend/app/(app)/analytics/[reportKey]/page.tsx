import Link from "next/link";

import AnalyticsEmbed from "./ui/AnalyticsEmbed";

const reportTitleMap: Record<string, string> = {
  chart_audit: "Chart Audit",
  exec_overview: "Executive Overview",
  revenue_cycle: "Revenue Cycle",
  clinical_delivery: "Clinical Delivery",
  compliance_risk: "Compliance & Risk",
};

type AnalyticsReportPageProps = {
  params:
    | {
      reportKey?: string;
    }
    | Promise<{
      reportKey?: string;
    }>;
};

async function resolveParams(
  params: AnalyticsReportPageProps["params"],
): Promise<{ reportKey?: string }> {
  if (typeof (params as { then?: unknown })?.then === "function") {
    return params as Promise<{ reportKey?: string }>;
  }
  return params;
}

function safeDecodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function titleFromReportKey(reportKey: string): string {
  const normalizedKey = reportKey.trim().toLowerCase();
  if (reportTitleMap[normalizedKey]) {
    return reportTitleMap[normalizedKey];
  }
  return normalizedKey
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

export default async function AnalyticsReportPage({ params }: AnalyticsReportPageProps) {
  const resolved = await resolveParams(params);
  const rawReportKey = typeof resolved.reportKey === "string" ? resolved.reportKey : "";
  const reportKey = safeDecodePathSegment(rawReportKey).trim();
  const reportTitle = reportKey ? titleFromReportKey(reportKey) : "Analytics Report";
  const refreshHref = reportKey ? `/analytics/${encodeURIComponent(reportKey)}` : "/analytics";

  return (
    <section className="min-h-screen bg-slate-50" data-testid="analytics-report-page">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-6 py-7 md:flex-row md:items-end md:justify-between">
          <div className="space-y-3">
            <Link
              href="/analytics"
              className="inline-flex text-xs font-medium uppercase tracking-[0.08em] text-slate-500 transition-colors hover:text-slate-700"
            >
              Back to analytics
            </Link>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Analytics Suite</p>
            <h1 className="text-3xl font-semibold text-slate-900">{reportTitle}</h1>
            {!reportKey ? (
              <p className="text-sm text-[var(--status-critical)]">
                Missing report key in route. Please return to Analytics and pick a report.
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            <Link
              href={refreshHref}
              className="inline-flex h-10 items-center rounded-md border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
            >
              Refresh
            </Link>
            <button
              type="button"
              className="inline-flex h-10 items-center rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-500"
            >
              Ask EI
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-8">
        {reportKey ? <AnalyticsEmbed reportKey={reportKey} /> : null}
      </div>
    </section>
  );
}

import Link from "next/link";

import AnalyticsEmbed from "./ui/AnalyticsEmbed";

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

export default async function AnalyticsReportPage({ params }: AnalyticsReportPageProps) {
  const resolved = await resolveParams(params);
  const rawReportKey = typeof resolved.reportKey === "string" ? resolved.reportKey : "";
  const reportKey = safeDecodePathSegment(rawReportKey).trim();

  return (
    <section className="space-y-[var(--space-16)]" data-testid="analytics-report-page">
      <header className="space-y-[var(--space-6)]">
        <Link
          href="/analytics"
          className="inline-flex text-xs font-medium text-[var(--brand-primary)] hover:text-[var(--brand-primary-600)]"
        >
          Back to analytics
        </Link>
        <h1 className="text-2xl font-semibold text-[var(--neutral-text)]">Analytics</h1>
        {reportKey ? (
          <p className="text-sm text-[var(--neutral-muted)]">
            Report key:{" "}
            <code className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--neutral-text)]">
              {reportKey}
            </code>
          </p>
        ) : (
          <p className="text-sm text-[var(--status-critical)]">
            Missing report key in route. Please return to Analytics and pick a report.
          </p>
        )}
      </header>
      {reportKey ? <AnalyticsEmbed reportKey={reportKey} /> : null}
    </section>
  );
}

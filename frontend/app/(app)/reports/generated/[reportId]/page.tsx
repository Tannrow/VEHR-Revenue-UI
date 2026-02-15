import Link from "next/link";

import GeneratedReportView from "./ui/GeneratedReportView";

type GeneratedReportPageProps = {
  params:
    | {
      reportId?: string;
    }
    | Promise<{
      reportId?: string;
    }>;
};

async function resolveParams(
  params: GeneratedReportPageProps["params"],
): Promise<{ reportId?: string }> {
  if (typeof (params as { then?: unknown })?.then === "function") {
    return params as Promise<{ reportId?: string }>;
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

export default async function GeneratedReportPage({ params }: GeneratedReportPageProps) {
  const resolved = await resolveParams(params);
  const rawReportId = typeof resolved.reportId === "string" ? resolved.reportId : "";
  const reportId = safeDecodePathSegment(rawReportId).trim();

  return (
    <section className="space-y-[var(--space-16)]" data-testid="generated-report-page">
      <header className="space-y-[var(--space-6)]">
        <Link
          href="/reports"
          className="inline-flex text-xs font-medium text-[var(--brand-primary)] hover:text-[var(--brand-primary-600)]"
        >
          Back to report templates
        </Link>
        <h1 className="text-2xl font-semibold text-[var(--neutral-text)]">Generated Report</h1>
        {reportId ? (
          <p className="text-sm text-[var(--neutral-muted)]">
            Report ID:{" "}
            <code className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--neutral-text)]">
              {reportId}
            </code>
          </p>
        ) : (
          <p className="text-sm text-[var(--status-critical)]">
            Missing report ID in route. Return to Reports and generate a report.
          </p>
        )}
      </header>

      {reportId ? <GeneratedReportView reportId={reportId} /> : null}
    </section>
  );
}

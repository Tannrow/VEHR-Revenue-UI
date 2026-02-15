import Link from "next/link";

import AnalyticsReportShell from "./ui/AnalyticsReportShell";

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
    <section data-testid="analytics-report-page">
      {reportKey ? (
        <AnalyticsReportShell reportKey={reportKey} />
      ) : (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
          Missing report key in route. <Link className="underline" href="/analytics">Return to Analytics</Link>.
        </div>
      )}
    </section>
  );
}

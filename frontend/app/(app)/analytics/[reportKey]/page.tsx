import AnalyticsEmbed from "./ui/AnalyticsEmbed";

type AnalyticsReportPageProps = {
  params: {
    reportKey: string;
  };
};

export default function AnalyticsReportPage({ params }: AnalyticsReportPageProps) {
  const reportKey = decodeURIComponent(params.reportKey);

  return (
    <section className="space-y-[var(--space-16)]" data-testid="analytics-report-page">
      <header className="space-y-[var(--space-6)]">
        <h1 className="text-2xl font-semibold text-[var(--neutral-text)]">Analytics</h1>
        <p className="text-sm text-[var(--neutral-muted)]">
          Report key:{" "}
          <code className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--neutral-text)]">
            {reportKey}
          </code>
        </p>
      </header>
      <AnalyticsEmbed reportKey={reportKey} />
    </section>
  );
}

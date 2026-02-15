"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";

type GeneratedReportSummary = {
  report_id: string;
  report_key: string;
  period_start: string;
  period_end: string;
  generated_at: string;
};

type GenerateWeeklyExecResponse = {
  report_id: string;
  report_key: string;
  period_start: string;
  period_end: string;
};

const WEEKLY_EXEC_REPORT_KEY = "weekly_exec_overview";

export default function ReportsPage() {
  const router = useRouter();
  const [latestWeeklyExec, setLatestWeeklyExec] = useState<GeneratedReportSummary | null>(null);
  const [isLoadingLatest, setIsLoadingLatest] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadLatest() {
      setIsLoadingLatest(true);
      setError(null);
      try {
        const latest = await apiFetch<GeneratedReportSummary>(
          `/api/v1/reports/generated/latest?report_key=${encodeURIComponent(WEEKLY_EXEC_REPORT_KEY)}`,
          { cache: "no-store" },
        );
        if (!isMounted) {
          return;
        }
        setLatestWeeklyExec(latest);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        if (loadError instanceof ApiError && loadError.status === 404) {
          setLatestWeeklyExec(null);
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load report templates.");
      } finally {
        if (isMounted) {
          setIsLoadingLatest(false);
        }
      }
    }

    void loadLatest();
    return () => {
      isMounted = false;
    };
  }, []);

  async function handleGenerateWeeklyExec() {
    setIsGenerating(true);
    setError(null);
    try {
      const generated = await apiFetch<GenerateWeeklyExecResponse>("/api/v1/reports/generate/weekly-exec", {
        method: "POST",
      });
      router.push(`/reports/generated/${encodeURIComponent(generated.report_id)}`);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Unable to generate weekly report.");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="space-y-[var(--space-16)]" data-testid="reports-templates-page">
      <AppLayoutPageConfig
        moduleLabel="Administration"
        pageTitle="Reports"
        subtitle="Generate and review executive overviews powered by analytics KPIs."
      />

      <header className="space-y-[var(--space-6)]">
        <h1 className="text-2xl font-semibold text-[var(--neutral-text)]">Report Templates</h1>
        <p className="text-sm text-[var(--neutral-muted)]">
          Generate organization-scoped narrative reports from governed KPI tables.
        </p>
      </header>

      {error ? (
        <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-12)] py-[var(--space-10)] text-sm text-[var(--status-critical)]">
          {error}
        </div>
      ) : null}

      <Card className="border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]">
        <CardHeader className="space-y-[var(--space-6)]">
          <CardTitle className="text-lg text-[var(--neutral-text)]">Weekly Executive Overview</CardTitle>
          <CardDescription className="text-sm text-[var(--neutral-muted)]">
            KPI cards, trends, and executive narrative scaffolding for the current week.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-[var(--space-12)]">
          <div className="text-sm text-[var(--neutral-muted)]">
            {isLoadingLatest ? (
              "Checking for latest generated report..."
            ) : latestWeeklyExec ? (
              <>
                Latest generated:{" "}
                <span className="font-medium text-[var(--neutral-text)]">
                  {new Date(latestWeeklyExec.generated_at).toLocaleString()}
                </span>
              </>
            ) : (
              "No generated report yet."
            )}
          </div>

          <div className="flex flex-wrap gap-[var(--space-8)]">
            <Button type="button" onClick={handleGenerateWeeklyExec} disabled={isGenerating}>
              {isGenerating ? "Generating..." : "Generate Weekly Executive Overview"}
            </Button>

            {latestWeeklyExec ? (
              <Button asChild variant="outline" type="button">
                <Link href={`/reports/generated/${encodeURIComponent(latestWeeklyExec.report_id)}`}>
                  Open Latest Generated
                </Link>
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import AnalyticsErrorBoundary from "@/components/analytics/AnalyticsErrorBoundary";
import EiPanel from "@/components/analytics/EiPanel";
import KpiStrip from "@/components/analytics/KpiStrip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";
import { apiFetch } from "@/lib/api";
import { fetchReports, type ReportListItem } from "@/lib/bi";
import {
  allowedCategoriesForRole,
  catalogTitleForReportKey,
  getReportCatalogEntry,
  isReportAllowedForRole,
  type ReportCategory,
  type UserRoleKey,
} from "@/lib/analytics/catalog";

import AnalyticsEmbed from "./AnalyticsEmbed";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type AnalyticsReportShellProps = {
  reportKey: string;
};

function categoryLabel(category: ReportCategory): string {
  switch (category) {
    case "executive":
      return "Executive";
    case "revenue":
      return "Revenue";
    case "clinical":
      return "Clinical";
    case "compliance":
      return "Compliance";
    default:
      return "Other";
  }
}

function categoryBadgeClass(category: ReportCategory): string {
  switch (category) {
    case "executive":
      return "border-indigo-200 bg-indigo-50 text-indigo-700";
    case "revenue":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "clinical":
      return "border-sky-200 bg-sky-50 text-sky-700";
    case "compliance":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

export default function AnalyticsReportShell({ reportKey }: AnalyticsReportShellProps) {
  const normalizedKey = reportKey.trim().toLowerCase();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eiOpen, setEiOpen] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const [meResponse, reportRows] = await Promise.all([
          apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
          fetchReports(),
        ]);
        if (!isMounted) return;
        setMe(meResponse);
        setReports(reportRows);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Unable to load analytics context.");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      isMounted = false;
    };
  }, []);

  const role = (me?.role ?? "").trim().toLowerCase() as UserRoleKey;
  const allowed = isReportAllowedForRole(normalizedKey, role);
  const catalog = getReportCatalogEntry(normalizedKey);
  const reportRecord = useMemo(
    () => reports.find((row) => row.report_key.toLowerCase() === normalizedKey) ?? null,
    [reports, normalizedKey],
  );

  const reportTitle = reportRecord?.name?.trim()
    || catalog?.title
    || catalogTitleForReportKey(normalizedKey);

  const reportDescription = catalog?.description ?? "Power BI report";
  const category: ReportCategory = catalog?.category ?? "other";

  const embedKey = `${normalizedKey}:${refreshNonce}`;

  return (
    <section className="min-h-screen bg-slate-50" data-testid="analytics-report-shell">
      <AppLayoutPageConfig
        moduleLabel="Governance"
        pageTitle={reportTitle}
        subtitle="Analytics Suite"
      />

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-6 py-7 md:flex-row md:items-end md:justify-between">
          <div className="space-y-3">
            <Link
              href="/analytics"
              className="inline-flex text-xs font-medium uppercase tracking-[0.08em] text-slate-500 transition-colors hover:text-slate-700"
            >
              Back to analytics
            </Link>

            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={categoryBadgeClass(category)}>
                {categoryLabel(category)}
              </Badge>
              {me ? (
                <Badge variant="outline" className="border-slate-200 bg-white text-slate-700">
                  Role: {me.role}
                </Badge>
              ) : null}
            </div>

            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Analytics Suite</p>
            <h1 className="text-3xl font-semibold text-slate-900">{reportTitle}</h1>
            <p className="max-w-2xl text-sm text-slate-600">{reportDescription}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setRefreshNonce((value) => value + 1);
              }}
            >
              Refresh
            </Button>
            <Button
              type="button"
              className="bg-indigo-600 text-white hover:bg-indigo-500"
              onClick={() => setEiOpen(true)}
              disabled={!me || !allowed || isLoading}
            >
              Ask EI
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-8">
        {isLoading ? (
          <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
            Loading analytics context...
          </div>
        ) : null}

        {!isLoading && error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
            {error}
          </div>
        ) : null}

        {!isLoading && !error && me && !allowed ? (
          <div className="rounded-2xl border border-slate-200 bg-white px-6 py-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Access restricted</h2>
            <p className="mt-2 text-sm text-slate-600">
              Your role does not have access to this report category.
            </p>
            <p className="mt-3 text-sm text-slate-600">
              Allowed categories for your role:{" "}
              <span className="font-medium text-slate-800">
                {allowedCategoriesForRole(role).map(categoryLabel).join(", ") || "none"}
              </span>
            </p>
            <div className="mt-5">
              <Button asChild variant="secondary">
                <Link href="/analytics">Return to Analytics</Link>
              </Button>
            </div>
          </div>
        ) : null}

        {!isLoading && !error && me && allowed ? (
          <>
            <KpiStrip reportKey={normalizedKey} key={`kpi-${embedKey}`} />

            <AnalyticsErrorBoundary resetKey={embedKey}>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <AnalyticsEmbed reportKey={normalizedKey} key={embedKey} />
              </div>
            </AnalyticsErrorBoundary>
          </>
        ) : null}
      </div>

      <EiPanel
        open={eiOpen}
        onClose={() => setEiOpen(false)}
        reportKey={normalizedKey}
        reportTitle={reportTitle}
      />
    </section>
  );
}


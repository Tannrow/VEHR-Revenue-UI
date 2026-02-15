"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AppLayoutPageConfig } from "@/lib/app-layout-config";
import { fetchReports, type ReportListItem } from "@/lib/bi";
import { apiFetch } from "@/lib/api";
import {
  allowedCategoriesForRole,
  getReportCatalogEntry,
  isReportAllowedForRole,
  type ReportCategory,
  type UserRoleKey,
} from "@/lib/analytics/catalog";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

function titleCaseFromKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

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

export default function AnalyticsIndexPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const [meResponse, rows] = await Promise.all([
          apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
          fetchReports(),
        ]);
        if (!isMounted) {
          return;
        }
        setMe(meResponse);
        setReports(rows);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load analytics reports.");
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
  const visibleReports = me
    ? reports.filter((item) => isReportAllowedForRole(item.report_key, role))
    : [];
  const allowedCategories = allowedCategoriesForRole(role);

  return (
    <section className="min-h-screen bg-slate-50" data-testid="analytics-index-page">
      <AppLayoutPageConfig
        moduleLabel="Governance"
        pageTitle="Analytics"
        subtitle="Explore tenant-scoped analytics reports."
      />

      <div className="mx-auto max-w-7xl px-6 py-8">
        <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Analytics Suite</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">Analytics</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Select a report to launch embedded Power BI analytics. Reports are filtered based on your role.
            </p>
          </div>

          {me ? (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-slate-200 bg-white text-slate-700">
                Role: {me.role}
              </Badge>
            </div>
          ) : null}
        </header>

        {isLoading ? (
          <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={`analytics-loading-${index}`}
                className="h-44 animate-pulse rounded-2xl border border-slate-200 bg-white shadow-sm"
              />
            ))}
          </div>
        ) : null}

        {!isLoading && error ? (
          <div className="mt-8 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
            {error}
          </div>
        ) : null}

        {!isLoading && !error ? (
          me ? (
            visibleReports.length > 0 ? (
              <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                {visibleReports.map((item) => {
                  const catalog = getReportCatalogEntry(item.report_key);
                  const title = item.name?.trim() || catalog?.title || titleCaseFromKey(item.report_key);
                  const description = catalog?.description || "Power BI report";
                  const category = catalog?.category ?? "other";
                  return (
                    <Card key={item.report_key} className="overflow-hidden rounded-2xl border-slate-200 bg-white shadow-sm">
                      <CardHeader className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="outline" className={categoryBadgeClass(category)}>
                            {categoryLabel(category)}
                          </Badge>
                        </div>
                        <CardTitle className="text-lg text-slate-900">{title}</CardTitle>
                        <CardDescription className="text-sm text-slate-600">{description}</CardDescription>
                      </CardHeader>
                      <CardContent className="flex items-center justify-between gap-3">
                        <Button asChild variant="secondary">
                          <Link href={`/analytics/${encodeURIComponent(item.report_key)}`}>Open Report</Link>
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <div className="mt-8 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
                {allowedCategories.length > 0
                  ? "No analytics reports are available for your role yet."
                  : "Your role does not have access to analytics reports."}
              </div>
            )
          ) : (
            <div className="mt-8 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
              Loading your analytics access...
            </div>
          )
        ) : null}
      </div>
    </section>
  );
}

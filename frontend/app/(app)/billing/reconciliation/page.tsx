"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";

import {
  ClaimDetailDrawer,
  LineFiltersBar,
  PaginationControls,
  ReconciliationSection,
  type ReconClaimRow,
  type ReconLineRow,
} from "../_components/recon-components";

type JobStatusResponse = {
  job_id: string;
  status: string;
  created_at?: string;
  finished_at?: string | null;
};

type ClaimResultsResponse = {
  level: "claim";
  count: number;
  rows: ReconClaimRow[];
};

type LineResultsResponse = {
  level: "line";
  count: number;
  offset: number;
  limit: number;
  rows: ReconLineRow[];
};

type LineResultsAltResponse = {
  items: ReconLineRow[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type LineMeta = {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

type ReconView = "claim" | "line";

const SECTION_KEYS = ["PAID", "PENDING", "NOT_RECEIVED", "DENIED", "NEEDS_REVIEW", "CLOSED"] as const;

function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function parseNumber(value: string | null | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return parsed;
}

function formatCurrency(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const numeric = typeof value === "number" ? value : Number.parseFloat(String(value));
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function normalizeLineResponse(
  payload: LineResultsResponse | LineResultsAltResponse,
  fallbackPage: number,
  fallbackPageSize: number,
): { rows: ReconLineRow[]; meta: LineMeta } {
  if ("rows" in payload) {
    const total = typeof payload.count === "number" ? payload.count : payload.rows.length;
    const limit = typeof payload.limit === "number" ? payload.limit : fallbackPageSize;
    const offset = typeof payload.offset === "number" ? payload.offset : (fallbackPage - 1) * limit;
    const page = Math.floor(offset / limit) + 1;
    const totalPages = Math.max(1, Math.ceil(total / limit));
    return { rows: payload.rows, meta: { page, pageSize: limit, total, totalPages } };
  }
  const total = typeof payload.total === "number" ? payload.total : payload.items.length;
  const pageSize = typeof payload.page_size === "number" ? payload.page_size : fallbackPageSize;
  const page = typeof payload.page === "number" ? payload.page : fallbackPage;
  const totalPages = typeof payload.total_pages === "number" ? payload.total_pages : Math.max(1, Math.ceil(total / pageSize));
  return { rows: payload.items ?? [], meta: { page, pageSize, total, totalPages } };
}

function mapClaimSection(row: ReconClaimRow): typeof SECTION_KEYS[number] {
  const status = (row.match_status || "").toUpperCase();
  const reason = (row.reason_code || "").toUpperCase();
  if (status === "PAID") return "PAID";
  if (status === "DENIED") return "DENIED";
  if (status === "CLOSED") return "CLOSED";
  if (status === "PENDING_NO_ERA" || status === "PENDING") return "PENDING";
  if (status === "NEEDS_REVIEW" && reason === "UNMATCHED_ERA") return "NOT_RECEIVED";
  return "NEEDS_REVIEW";
}

function computeTotals(rows: ReconClaimRow[]) {
  const totals = rows.reduce(
    (acc, row) => {
      const billed = typeof row.billed_total === "number" ? row.billed_total : Number(row.billed_total);
      const paid = typeof row.paid_total === "number" ? row.paid_total : Number(row.paid_total);
      const variance = typeof row.variance_total === "number" ? row.variance_total : Number(row.variance_total);
      if (Number.isFinite(billed)) acc.billed += billed;
      if (Number.isFinite(paid)) acc.paid += paid;
      if (Number.isFinite(variance)) acc.variance += variance;
      return acc;
    },
    { billed: 0, paid: 0, variance: 0 },
  );
  return {
    billed: formatCurrency(totals.billed),
    paid: formatCurrency(totals.paid),
    variance: formatCurrency(totals.variance),
  };
}

function buildLineQuery({
  jobId,
  page,
  pageSize,
  matchStatus,
  billedTrack,
}: {
  jobId: string;
  page: number;
  pageSize: number;
  matchStatus: string;
  billedTrack: string;
}) {
  const params = new URLSearchParams();
  params.set("level", "line");
  params.set("limit", String(pageSize));
  params.set("offset", String((page - 1) * pageSize));
  if (matchStatus) params.set("match_status", matchStatus);
  if (billedTrack) params.set("billed_track", billedTrack);
  return `/api/v1/billing/recon/import/${jobId}/results?${params.toString()}`;
}

function deriveHealthWarning(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  if ("current_week_has_run" in data) {
    return (data as { current_week_has_run?: boolean }).current_week_has_run === false
      ? "No reconciliation run this week"
      : null;
  }
  if ("current_week" in data && data.current_week && typeof data.current_week === "object") {
    const hasRun = (data.current_week as { has_run?: boolean }).has_run;
    if (hasRun === false) return "No reconciliation run this week";
  }
  if ("weeks" in data && Array.isArray(data.weeks)) {
    const weeks = data.weeks as Array<{ week_start?: string; has_run?: boolean }>;
    if (weeks.length > 0) {
      const latest = weeks.reduce((current, candidate) => {
        const currentDate = current.week_start ? Date.parse(current.week_start) : 0;
        const candidateDate = candidate.week_start ? Date.parse(candidate.week_start) : 0;
        return candidateDate > currentDate ? candidate : current;
      }, weeks[0]);
      if (latest.has_run === false) return "No reconciliation run this week";
    }
  }
  return null;
}

export default function ReconciliationPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const jobId = searchParams.get("job_id") ?? "";
  const view = (searchParams.get("view") === "line" ? "line" : "claim") as ReconView;
  const page = parseNumber(searchParams.get("page"), 1);
  const pageSize = 100;
  const matchStatus = searchParams.get("match_status") ?? "";
  const billedTrack = searchParams.get("billed_track") ?? "";

  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [claimRows, setClaimRows] = useState<ReconClaimRow[]>([]);
  const [claimLoading, setClaimLoading] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const [lineRows, setLineRows] = useState<ReconLineRow[]>([]);
  const [lineMeta, setLineMeta] = useState<LineMeta>({ page: 1, pageSize: 100, total: 0, totalPages: 1 });
  const [lineLoading, setLineLoading] = useState(false);
  const [lineError, setLineError] = useState<string | null>(null);

  const [selectedClaim, setSelectedClaim] = useState<ReconClaimRow | null>(null);
  const [claimLines, setClaimLines] = useState<ReconLineRow[]>([]);
  const [claimLineLoading, setClaimLineLoading] = useState(false);
  const [claimLineError, setClaimLineError] = useState<string | null>(null);
  const [claimLineNote, setClaimLineNote] = useState<string | null>(null);

  const [healthWarning, setHealthWarning] = useState<string | null>(null);

  const updateQuery = useCallback(
    (patch: Record<string, string | null | undefined>, replace = false) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(patch).forEach(([key, value]) => {
        if (value == null || value === "") {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      });
      const query = params.toString();
      const href = query ? `${pathname}?${query}` : pathname;
      if (replace) {
        router.replace(href);
      } else {
        router.push(href);
      }
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    async function loadStatus() {
      try {
        setStatusError(null);
        const status = await apiFetch<JobStatusResponse>(`/api/v1/billing/recon/import/${jobId}`, { cache: "no-store" });
        if (!active) return;
        setJobStatus(status);
      } catch (error) {
        if (!active) return;
        setStatusError(toErrorMessage(error, "Failed to load job status"));
      }
    }
    void loadStatus();
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    let active = true;
    async function loadHealth() {
      try {
        const data = await apiFetch<unknown>("/api/v1/billing/recon/audit/health?weeks=8", { cache: "no-store" });
        if (!active) return;
        setHealthWarning(deriveHealthWarning(data));
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          setHealthWarning(null);
          return;
        }
        setHealthWarning(null);
      }
    }
    void loadHealth();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!jobId || view !== "claim") return;
    let active = true;

    async function loadClaims() {
      try {
        setClaimLoading(true);
        setClaimError(null);
        const data = await apiFetch<ClaimResultsResponse>(
          `/api/v1/billing/recon/import/${jobId}/results?level=claim`,
          { cache: "no-store" },
        );
        if (!active) return;
        setClaimRows(
          data.rows
            .slice()
            .sort((a, b) => (a.account_id ?? "").localeCompare(b.account_id ?? "") || a.id - b.id),
        );
      } catch (error) {
        if (!active) return;
        setClaimError(toErrorMessage(error, "Failed to load claim results"));
      } finally {
        if (active) setClaimLoading(false);
      }
    }

    void loadClaims();
    return () => {
      active = false;
    };
  }, [jobId, view]);

  useEffect(() => {
    if (!jobId || view !== "line") return;
    let active = true;

    async function loadLines() {
      try {
        setLineLoading(true);
        setLineError(null);
        const url = buildLineQuery({ jobId, page, pageSize, matchStatus, billedTrack });
        const data = await apiFetch<LineResultsResponse | LineResultsAltResponse>(url, { cache: "no-store" });
        if (!active) return;
        const normalized = normalizeLineResponse(data, page, pageSize);
        setLineRows(normalized.rows);
        setLineMeta(normalized.meta);
      } catch (error) {
        if (!active) return;
        setLineError(toErrorMessage(error, "Failed to load line results"));
      } finally {
        if (active) setLineLoading(false);
      }
    }

    void loadLines();
    return () => {
      active = false;
    };
  }, [jobId, view, page, pageSize, matchStatus, billedTrack]);

  useEffect(() => {
    if (!selectedClaim || !jobId) return;
    if (!selectedClaim.account_id) {
      setClaimLines([]);
      setClaimLineNote("Line-level matching is unavailable for claims without an account ID.");
      return;
    }
    let active = true;

    async function loadClaimLines() {
      try {
        setClaimLineLoading(true);
        setClaimLineError(null);
        setClaimLineNote(null);
        const params = new URLSearchParams();
        params.set("level", "line");
        params.set("page", "1");
        params.set("page_size", "100");
        params.set("limit", "100");
        params.set("offset", "0");
        params.set("claim_id", selectedClaim.account_id ?? "");
        const data = await apiFetch<LineResultsResponse | LineResultsAltResponse>(
          `/api/v1/billing/recon/import/${jobId}/results?${params.toString()}`,
          { cache: "no-store" },
        );
        if (!active) return;
        const normalized = normalizeLineResponse(data, 1, 100);
        const filtered = normalized.rows.filter((row) => row.account_id === selectedClaim.account_id);
        setClaimLines(filtered);
        if (normalized.total > normalized.rows.length) {
          setClaimLineNote("Showing the first page of line items. Filtered results may be incomplete.");
        }
      } catch (error) {
        if (!active) return;
        setClaimLineError(toErrorMessage(error, "Failed to load claim line items"));
      } finally {
        if (active) setClaimLineLoading(false);
      }
    }

    void loadClaimLines();
    return () => {
      active = false;
    };
  }, [jobId, selectedClaim]);

  const sections = useMemo(() => {
    const grouped: Record<(typeof SECTION_KEYS)[number], ReconClaimRow[]> = {
      PAID: [],
      PENDING: [],
      NOT_RECEIVED: [],
      DENIED: [],
      NEEDS_REVIEW: [],
      CLOSED: [],
    };
    for (const row of claimRows) {
      grouped[mapClaimSection(row)].push(row);
    }
    return grouped;
  }, [claimRows]);

  if (!jobId) {
    return (
      <div className="flex flex-col gap-6">
        <div className="space-y-2">
          <p className="text-sm font-semibold text-slate-500">Billing</p>
          <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Reconciliation</h1>
          <p className="max-w-2xl text-base text-slate-600">Select an import job to view reconciliation results.</p>
        </div>
        <Card className="bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg text-slate-900">No job selected</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600">
            Run a new ERA import to generate reconciliation results.
            <Button asChild variant="outline">
              <Link href="/billing/era-import">Start an import</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-sm font-semibold text-slate-500">Billing</p>
          <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Reconciliation</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span>Job</span>
            <Badge variant="secondary">{jobId}</Badge>
            {jobStatus?.status ? <Badge variant="outline">{jobStatus.status}</Badge> : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                updateQuery({ job_id: jobId }, true);
              }}
            >
              <RefreshCcw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
          {statusError ? <p className="text-sm text-rose-600">{statusError}</p> : null}
        </div>
        <div className="flex flex-col gap-2">
          {healthWarning ? (
            <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <AlertTriangle className="h-4 w-4" />
              {healthWarning}
            </div>
          ) : null}
        </div>
      </div>

      <Tabs
        value={view}
        onValueChange={(value) => {
          const nextView = value === "line" ? "line" : "claim";
          updateQuery({ view: nextView, page: "1" }, false);
        }}
      >
        <TabsList>
          <TabsTrigger value="claim">Claim view</TabsTrigger>
          <TabsTrigger value="line">Line view</TabsTrigger>
        </TabsList>
      </Tabs>

      {view === "claim" ? (
        <div className="space-y-4">
          {claimLoading ? <p className="text-sm text-slate-500">Loading claim results...</p> : null}
          {claimError ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
              {claimError}
            </div>
          ) : null}
          {SECTION_KEYS.map((key) => {
            const displayRows = sections[key].map((row) => ({
              ...row,
              billed_total: formatCurrency(row.billed_total),
              paid_total: formatCurrency(row.paid_total),
              variance_total: formatCurrency(row.variance_total),
            }));
            return (
              <ReconciliationSection
                key={key}
                title={key.replace("_", " ")}
                rows={displayRows}
                totals={computeTotals(sections[key])}
                onSelect={(row) => setSelectedClaim(row)}
              />
            );
          })}
        </div>
      ) : (
        <div className="space-y-4">
          <LineFiltersBar
            matchStatus={matchStatus}
            billedTrack={billedTrack}
            onMatchStatusChange={(value) => updateQuery({ match_status: value, page: "1" }, false)}
            onBilledTrackChange={(value) => updateQuery({ billed_track: value, page: "1" }, false)}
          />
          {lineError ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
              {lineError}
            </div>
          ) : null}
          {lineLoading ? (
            <p className="text-sm text-slate-500">Loading line results...</p>
          ) : (
            <Card className="bg-white shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base text-slate-900">Line results</CardTitle>
                <Badge variant="secondary">{lineMeta.total} lines</Badge>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="overflow-hidden rounded-lg border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-50">
                      <TableRow>
                        <TableHead className="text-xs uppercase tracking-[0.16em] text-slate-500">Claim</TableHead>
                        <TableHead className="text-xs uppercase tracking-[0.16em] text-slate-500">DOS</TableHead>
                        <TableHead className="text-xs uppercase tracking-[0.16em] text-slate-500">Proc</TableHead>
                        <TableHead className="text-right text-xs uppercase tracking-[0.16em] text-slate-500">Billed</TableHead>
                        <TableHead className="text-right text-xs uppercase tracking-[0.16em] text-slate-500">Paid</TableHead>
                        <TableHead className="text-right text-xs uppercase tracking-[0.16em] text-slate-500">Variance</TableHead>
                        <TableHead className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</TableHead>
                        <TableHead className="text-xs uppercase tracking-[0.16em] text-slate-500">Reason</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {lineRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-sm text-slate-500">
                            No line results returned.
                          </TableCell>
                        </TableRow>
                      ) : (
                        lineRows.map((row) => (
                          <TableRow key={row.id} className="text-slate-700">
                            <TableCell className="font-medium text-slate-900">{row.account_id ?? "—"}</TableCell>
                            <TableCell>
                              {row.dos_from ?? "—"}
                              {row.dos_to && row.dos_to !== row.dos_from ? ` - ${row.dos_to}` : ""}
                            </TableCell>
                            <TableCell>{row.proc_code ?? "—"}</TableCell>
                            <TableCell className="text-right">{formatCurrency(row.billed_amount)}</TableCell>
                            <TableCell className="text-right">{formatCurrency(row.paid_amount)}</TableCell>
                            <TableCell className="text-right">{formatCurrency(row.variance_amount)}</TableCell>
                            <TableCell>{row.match_status}</TableCell>
                            <TableCell className="text-slate-500">{row.reason_code ?? "—"}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
                <PaginationControls
                  page={lineMeta.page}
                  pageSize={lineMeta.pageSize}
                  total={lineMeta.total}
                  totalPages={lineMeta.totalPages}
                  onPageChange={(nextPage) => updateQuery({ page: String(nextPage), page_size: "100" }, false)}
                />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <ClaimDetailDrawer
        open={Boolean(selectedClaim)}
        claim={selectedClaim}
        lines={claimLines.map((row) => ({
          ...row,
          billed_amount: formatCurrency(row.billed_amount),
          paid_amount: formatCurrency(row.paid_amount),
          variance_amount: formatCurrency(row.variance_amount),
        }))}
        loading={claimLineLoading}
        error={claimLineError}
        note={claimLineNote}
        onClose={() => setSelectedClaim(null)}
      />
    </div>
  );
}

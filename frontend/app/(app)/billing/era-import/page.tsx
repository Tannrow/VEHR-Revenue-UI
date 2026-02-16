"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Clock, Loader2, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";

import { SummaryStatCard, UploadCard } from "../_components/recon-components";

type ImportResponse = {
  job_id: string;
  status: string;
  duplicate?: boolean;
  prior_job_id?: string | null;
};

type StatusResponse = {
  job_id: string;
  status: string;
  pages_detected_era?: number | null;
  tables_detected_era?: number | null;
  claims_extracted_era?: number | null;
  lines_extracted_era?: number | null;
  pages_detected_billed?: number | null;
  lines_extracted_billed?: number | null;
  skipped_counts_json?: Record<string, Record<string, number> | number> | null;
  matched_claims?: number | null;
  unmatched_era_claims?: number | null;
  unmatched_billed_claims?: number | null;
  underpaid_claims?: number | null;
  denied_claims?: number | null;
  needs_review_claims?: number | null;
  closed_claims?: number | null;
  output_xlsx_path?: string | null;
  error_message?: string | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
};

const BILLED_TRACK_OPTIONS = ["CHPW", "Coordinated Care", "Wellpoint", "Billing"] as const;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function statusBadgeVariant(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") return "default";
  if (normalized === "failed") return "destructive";
  if (normalized === "processing") return "secondary";
  return "outline";
}

function statusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatCount(value?: number | null): string {
  if (value == null) return "—";
  return value.toLocaleString();
}

function flattenSkippedCounts(raw?: StatusResponse["skipped_counts_json"]): Array<{ label: string; value: number }> {
  if (!raw || typeof raw !== "object") return [];
  const entries: Array<{ label: string; value: number }> = [];
  for (const [groupKey, groupValue] of Object.entries(raw)) {
    if (typeof groupValue === "number") {
      entries.push({ label: groupKey, value: groupValue });
      continue;
    }
    if (groupValue && typeof groupValue === "object") {
      for (const [key, value] of Object.entries(groupValue)) {
        if (typeof value === "number") {
          entries.push({ label: `${groupKey}: ${key}`, value });
        }
      }
    }
  }
  return entries;
}

export default function EraImportPage() {
  const [eraFile, setEraFile] = useState<File | null>(null);
  const [billedFile, setBilledFile] = useState<File | null>(null);
  const [billedTrack, setBilledTrack] = useState("");

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<StatusResponse | null>(null);
  const [duplicateJobId, setDuplicateJobId] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(eraFile && billedFile && billedTrack);

  const skippedCounts = useMemo(() => flattenSkippedCounts(jobStatus?.skipped_counts_json), [jobStatus]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      setIsPolling(true);
      try {
        const latest = await apiFetch<StatusResponse>(`/api/v1/billing/recon/import/${jobId}`, { cache: "no-store" });
        if (!active) return;
        setJobStatus(latest);
        if (TERMINAL_STATUSES.has(latest.status.toLowerCase())) {
          setIsPolling(false);
          return;
        }
      } catch (pollError) {
        if (!active) return;
        setError(toErrorMessage(pollError, "Failed to load job status"));
        setIsPolling(false);
        return;
      }
      timer = setTimeout(poll, 2000);
    }

    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eraFile || !billedFile || !billedTrack) return;

    setError(null);
    setIsSubmitting(true);
    setDuplicateJobId(null);

    try {
      const formData = new FormData();
      formData.append("era_pdf", eraFile, eraFile.name);
      formData.append("billed_pdf", billedFile, billedFile.name);
      formData.append("billed_track", billedTrack);

      const response = await apiFetch<ImportResponse>("/api/v1/billing/recon/import", {
        method: "POST",
        body: formData,
      });

      setJobId(response.job_id);
      setJobStatus({ job_id: response.job_id, status: response.status });
      if (response.duplicate) {
        setDuplicateJobId(response.prior_job_id ?? response.job_id);
      }
    } catch (submitError) {
      setError(toErrorMessage(submitError, "Failed to submit reconciliation job."));
    } finally {
      setIsSubmitting(false);
    }
  }

  const statusIcon = jobStatus?.status ? jobStatus.status.toLowerCase() : "";
  const showCompleted = jobStatus?.status?.toLowerCase() === "completed";
  const showFailed = jobStatus?.status?.toLowerCase() === "failed";

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-500">Billing</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">ERA Import</h1>
        <p className="max-w-3xl text-base text-slate-600">
          Upload ERA and billed claims PDFs, then reconcile automatically.
        </p>
      </div>

      <form className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]" onSubmit={handleSubmit}>
        <div className="space-y-5">
          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
          {duplicateJobId ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
              Already imported.{" "}
              <Link className="font-semibold underline" href={`/billing/reconciliation?job_id=${duplicateJobId}&view=claim`}>
                View reconciliation
              </Link>
            </div>
          ) : null}

          <UploadCard
            title="ERA PDF"
            description="Payer remittance advice document."
            file={eraFile}
            onFileChange={(file) => {
              setEraFile(file);
              setError(null);
            }}
            onError={(message) => setError(message)}
          />
          <UploadCard
            title="Billed Claims PDF"
            description="The billed claims report from your clearinghouse."
            file={billedFile}
            onFileChange={(file) => {
              setBilledFile(file);
              setError(null);
            }}
            onError={(message) => setError(message)}
          />

          <Card className="bg-[var(--neutral-panel)]">
            <CardHeader className="space-y-1">
              <CardTitle className="text-base text-slate-900">Billed PDF Type</CardTitle>
              <p className="text-sm text-slate-500">Select the report layout so we can reconcile accurately.</p>
            </CardHeader>
            <CardContent>
              <select
                className="h-10 w-full rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--neutral-border)_72%,white)] bg-[var(--neutral-panel)] px-3 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={billedTrack}
                onChange={(event) => {
                  setBilledTrack(event.target.value);
                  setError(null);
                }}
                required
              >
                <option value="">Select billed PDF type</option>
                {BILLED_TRACK_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={!canSubmit || isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                "Import & Reconcile"
              )}
            </Button>
            {jobStatus?.status ? (
              <Badge variant={statusBadgeVariant(jobStatus.status)}>
                {statusLabel(jobStatus.status)}
              </Badge>
            ) : null}
            {isPolling && !showCompleted && !showFailed ? (
              <span className="flex items-center gap-2 text-xs text-slate-500">
                <Clock className="h-3.5 w-3.5" />
                Polling status...
              </span>
            ) : null}
          </div>
        </div>

        <div className="space-y-4">
          <Card className="bg-white shadow-sm">
            <CardHeader className="space-y-2">
              <CardTitle className="text-lg text-slate-900">Job status</CardTitle>
              {jobStatus?.status ? (
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  {statusIcon === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : null}
                  {statusIcon === "failed" ? <TriangleAlert className="h-4 w-4 text-rose-500" /> : null}
                  <span>{statusLabel(jobStatus.status)}</span>
                </div>
              ) : (
                <p className="text-sm text-slate-500">Submit a job to see status.</p>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {showFailed ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {jobStatus?.error_message || "Recon failed. Please retry or contact support."}
                </div>
              ) : null}
              {showCompleted ? (
                <Button asChild variant="outline">
                  <Link href={`/billing/reconciliation?job_id=${jobId ?? ""}&view=claim${billedTrack ? `&billed_track=${encodeURIComponent(billedTrack)}` : ""}`}>
                    View Reconciliation
                  </Link>
                </Button>
              ) : null}
            </CardContent>
          </Card>

          {showCompleted ? (
            <div className="space-y-4">
              <Card className="bg-white shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base text-slate-900">ERA extraction</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2">
                  <SummaryStatCard label="Pages" value={formatCount(jobStatus?.pages_detected_era)} />
                  <SummaryStatCard label="Tables" value={formatCount(jobStatus?.tables_detected_era)} />
                  <SummaryStatCard label="Claims" value={formatCount(jobStatus?.claims_extracted_era)} />
                  <SummaryStatCard label="Lines" value={formatCount(jobStatus?.lines_extracted_era)} />
                </CardContent>
              </Card>

              <Card className="bg-white shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base text-slate-900">Billed extraction</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2">
                  <SummaryStatCard label="Pages" value={formatCount(jobStatus?.pages_detected_billed)} />
                  <SummaryStatCard label="Lines" value={formatCount(jobStatus?.lines_extracted_billed)} />
                </CardContent>
              </Card>

              <Card className="bg-white shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base text-slate-900">Reconciliation results</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2">
                  <SummaryStatCard label="Matched" value={formatCount(jobStatus?.matched_claims)} />
                  <SummaryStatCard label="Unmatched ERA" value={formatCount(jobStatus?.unmatched_era_claims)} />
                  <SummaryStatCard label="Unmatched billed" value={formatCount(jobStatus?.unmatched_billed_claims)} />
                  <SummaryStatCard label="Underpaid" value={formatCount(jobStatus?.underpaid_claims)} />
                  <SummaryStatCard label="Denied" value={formatCount(jobStatus?.denied_claims)} />
                  <SummaryStatCard label="Needs review" value={formatCount(jobStatus?.needs_review_claims)} />
                  <SummaryStatCard label="Closed" value={formatCount(jobStatus?.closed_claims)} />
                </CardContent>
              </Card>

              <Card className="bg-white shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base text-slate-900">Skipped counts</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {skippedCounts.length === 0 ? (
                    <p className="text-sm text-slate-500">No skipped counts reported.</p>
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {skippedCounts.map((item) => (
                        <div
                          key={`${item.label}-${item.value}`}
                          className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
                        >
                          <span>{item.label}</span>
                          <span className="font-semibold">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}
        </div>
      </form>
    </div>
  );
}

"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import MetricCard from "../_components/MetricCard";
import { UploadCard } from "./_components/recon-components";

const billingItems = [
  { item: "Claims pending", status: "Review needed", risk: "Medium" },
  { item: "Remittance exceptions", status: "Attention required", risk: "High" },
  { item: "Submission queue", status: "On track", risk: "Low" },
];

const auditTrail = [
  "Export run initiated for current cycle",
  "Manual adjustment logged by billing supervisor",
  "Exception queue reconciled for prior period",
];

const BILLED_TRACK_OPTIONS = ["CHPW", "Coordinated Care", "Wellpoint", "Billing"] as const;

type ImportResponse = {
  job_id: string;
  status: string;
  duplicate?: boolean;
  prior_job_id?: string | null;
};

function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

export default function BillingPage() {
  const [eraFile, setEraFile] = useState<File | null>(null);
  const [billedFile, setBilledFile] = useState<File | null>(null);
  const [billedTrack, setBilledTrack] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [duplicateJobId, setDuplicateJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(eraFile && billedFile && billedTrack);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eraFile || !billedFile || !billedTrack) return;

    setError(null);
    setIsSubmitting(true);
    setDuplicateJobId(null);
    setJobId(null);

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
      if (response.duplicate) {
        setDuplicateJobId(response.prior_job_id ?? response.job_id);
      }
    } catch (submitError) {
      setError(toErrorMessage(submitError, "Failed to submit reconciliation job."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Oversight</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Billing</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Status-first billing visibility for leadership and operations.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Claims pending" value="24" hint="Awaiting review" />
        <MetricCard label="Exceptions" value="5" hint="Escalate today" />
        <MetricCard label="Export status" value="In progress" hint="Current pay cycle" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">ERA Import</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-slate-600">
            Upload ERA and billed claims PDFs to reconcile in one pass.
            <Button asChild variant="outline">
              <Link href="/billing/era-import">Open full import page</Link>
            </Button>
          </CardContent>
        </Card>
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Reconciliation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-slate-600">
            Review claim- and line-level reconciliation results.
            <Button asChild variant="outline">
              <Link href="/billing/reconciliation">View results</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-white shadow-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-xl text-slate-900">Quick ERA Import</CardTitle>
          <p className="text-sm text-slate-500">Drop PDFs here to start a reconciliation job.</p>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]" onSubmit={handleSubmit}>
            <div className="space-y-4">
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
            </div>

            <div className="space-y-3">
              <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                Billed PDF type
                <select
                  className="mt-1 h-10 w-full rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--neutral-border)_72%,white)] bg-[var(--neutral-panel)] px-3 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
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
              </label>

              <Button type="submit" disabled={!canSubmit || isSubmitting} className="w-full">
                {isSubmitting ? "Uploading..." : "Import & Reconcile"}
              </Button>

              {jobId ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  Job submitted.{" "}
                  <Link className="font-semibold underline" href={`/billing/reconciliation?job_id=${jobId}&view=claim`}>
                    View reconciliation
                  </Link>
                </div>
              ) : null}
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Billing status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {billingItems.map((row) => (
              <div key={row.item} className="rounded-lg bg-slate-50 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{row.item}</p>
                  <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${row.risk === "High" ? "ui-status-error" : row.risk === "Medium" ? "ui-status-warning" : "ui-status-success"}`}>
                    {row.risk}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{row.status}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Audit trail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {auditTrail.map((item) => (
              <div key={item} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                {item}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

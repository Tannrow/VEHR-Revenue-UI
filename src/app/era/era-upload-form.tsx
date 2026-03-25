"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { isFetchFailedMessage } from "@/lib/error-messages";

type EraFileResponse = {
  id: string;
  file_name: string;
  status: string;
  payer_name_raw: string | null;
  received_date: string | null;
  error_detail: string | null;
  request_id: string | null;
  created_at: string;
};

type EraWorkItem = {
  id: string;
  type: string;
  payer_name: string;
  claim_ref: string;
  dollars_cents: number;
  status: string;
  created_at: string;
};

type EraReportResponse = {
  era_file_id: string;
  claim_count: number;
  line_count: number;
  work_item_count: number;
  total_paid_cents: number;
  total_adjustment_cents: number;
  total_patient_resp_cents: number;
  net_cents: number;
  reconciled: boolean;
  declared_total_missing: boolean;
  phi_scan_passed: boolean;
  phi_hit_count: number;
  finalized: boolean;
  review_required: boolean;
  conflict_count: number;
  review_required_count: number;
  low_confidence_count: number;
  critical_missing_count: number;
  deterministic_row_count: number;
  llm_row_count: number;
  merged_row_count: number;
  created_at: string;
  top_work_items: EraWorkItem[];
};

type ProcessErrorResponse = {
  detail?: string | { error_code?: string; current_status?: string; era_file_id?: string };
  error?: string;
  stage?: string;
  error_code?: string;
  request_id?: string;
};

type UploadState = {
  status: "idle" | "submitting" | "success" | "error";
  message: string | null;
  uploadedFile: EraFileResponse | null;
  processedFile: EraFileResponse | null;
  report: EraReportResponse | null;
  reportMessage: string | null;
  processError: string | null;
  payload: EraFileResponse | EraFileResponse[] | ProcessErrorResponse | EraReportResponse | null;
};

const INITIAL_STATE: UploadState = {
  status: "idle",
  message: null,
  uploadedFile: null,
  processedFile: null,
  report: null,
  reportMessage: null,
  processError: null,
  payload: null,
};

function formatCents(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value / 100);
}

function getStatusTone(status: string): string {
  switch (status) {
    case "COMPLETE":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "ERROR":
      return "border-rose-500/40 bg-rose-500/10 text-rose-200";
    case "UPLOADED":
    case "PROCESSING_EXTRACT":
    case "PROCESSING_STRUCTURING":
    default:
      return "border-amber-500/40 bg-amber-500/10 text-amber-200";
  }
}

function formatProcessError(payload: ProcessErrorResponse | null, statusCode: number): string {
  if (!payload) {
    return `Processing failed with status ${statusCode}.`;
  }

  if (typeof payload.error === "string" && payload.error.trim()) {
    return payload.error.trim();
  }

  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail.trim();
  }

  if (payload.error_code) {
    return `Processing failed: ${payload.error_code}.`;
  }

  if (payload.detail && typeof payload.detail === "object" && payload.detail.error_code) {
    return `Processing blocked: ${payload.detail.error_code}.`;
  }

  return `Processing failed with status ${statusCode}.`;
}

function ResultCard({
  label,
  file,
}: {
  label: string;
  file: EraFileResponse;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-black/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">{label}</p>
          <h3 className="text-base font-semibold text-white break-all">{file.file_name}</h3>
        </div>
        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${getStatusTone(file.status)}`}>
          {file.status.replaceAll("_", " ")}
        </span>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-zinc-300 md:grid-cols-2">
        <div>
          <dt className="text-zinc-500">ERA File ID</dt>
          <dd className="break-all text-white">{file.id}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Created</dt>
          <dd className="text-white">{new Date(file.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Payer</dt>
          <dd className="text-white">{file.payer_name_raw ?? "Pending extraction"}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Received date</dt>
          <dd className="text-white">{file.received_date ?? "Pending extraction"}</dd>
        </div>
        {file.request_id ? (
          <div className="md:col-span-2">
            <dt className="text-zinc-500">Request ID</dt>
            <dd className="break-all text-white">{file.request_id}</dd>
          </div>
        ) : null}
        {file.error_detail ? (
          <div className="md:col-span-2">
            <dt className="text-zinc-500">Error detail</dt>
            <dd className="break-all text-rose-200">{file.error_detail}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}

function ReviewCard({ report }: { report: EraReportResponse }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-black/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Results review</p>
          <h3 className="text-base font-semibold text-white">Processed ERA summary</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span
            className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
              report.finalized
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                : "border-amber-500/40 bg-amber-500/10 text-amber-200"
            }`}
          >
            {report.finalized ? "Finalized" : "Needs review"}
          </span>
          <span
            className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
              report.reconciled
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                : "border-amber-500/40 bg-amber-500/10 text-amber-200"
            }`}
          >
            {report.reconciled ? "Reconciled" : "Not reconciled"}
          </span>
        </div>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-zinc-300 md:grid-cols-4">
        <div>
          <dt className="text-zinc-500">Claims</dt>
          <dd className="text-white">{report.claim_count}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Claim lines</dt>
          <dd className="text-white">{report.line_count}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Work items</dt>
          <dd className="text-white">{report.work_item_count}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Created</dt>
          <dd className="text-white">{new Date(report.created_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Paid</dt>
          <dd className="text-white">{formatCents(report.total_paid_cents)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Adjustments</dt>
          <dd className="text-white">{formatCents(report.total_adjustment_cents)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Patient responsibility</dt>
          <dd className="text-white">{formatCents(report.total_patient_resp_cents)}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Net</dt>
          <dd className="text-white">{formatCents(report.net_cents)}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap gap-2 text-xs text-zinc-300">
        <span className="rounded-full border border-zinc-700 px-3 py-1">
          PHI scan: {report.phi_scan_passed ? "passed" : "attention needed"}
        </span>
        <span className="rounded-full border border-zinc-700 px-3 py-1">
          Declared totals: {report.declared_total_missing ? "missing" : "present"}
        </span>
        <span className="rounded-full border border-zinc-700 px-3 py-1">
          Review rows: {report.review_required_count}
        </span>
        <span className="rounded-full border border-zinc-700 px-3 py-1">
          Conflicts: {report.conflict_count}
        </span>
        <span className="rounded-full border border-zinc-700 px-3 py-1">
          Deterministic / LLM / merged: {report.deterministic_row_count} / {report.llm_row_count} / {report.merged_row_count}
        </span>
      </div>

      {report.top_work_items.length > 0 ? (
        <div className="mt-6 space-y-3">
          <h4 className="text-sm font-semibold text-white">Top work items</h4>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
              <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Claim</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Payer</th>
                  <th className="px-4 py-3 font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800 bg-zinc-950/40 text-zinc-200">
                {report.top_work_items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-3 align-top text-white">{item.claim_ref}</td>
                    <td className="px-4 py-3 align-top">{item.type}</td>
                    <td className="px-4 py-3 align-top">{item.payer_name}</td>
                    <td className="px-4 py-3 align-top">{formatCents(item.dollars_cents)}</td>
                    <td className="px-4 py-3 align-top">{item.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href={`/era/${report.era_file_id}`}
          className="inline-flex rounded-md border border-white px-4 py-2 text-sm font-medium text-white transition hover:bg-white hover:text-black"
        >
          Open ERA lab
        </Link>
      </div>
    </div>
  );
}

function RecentEraFilesCard({ files }: { files: EraFileResponse[] }) {
  if (files.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-black/40 p-4 text-sm text-zinc-400">
        No ERA files have been uploaded yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-black/40">
      <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
        <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">File</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Payer</th>
            <th className="px-4 py-3 font-medium">Created</th>
            <th className="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-950/40 text-zinc-200">
          {files.map((file) => (
            <tr key={file.id}>
              <td className="px-4 py-3 align-top">
                <div className="space-y-1">
                  <p className="max-w-xl break-all font-medium text-white">{file.file_name}</p>
                  <p className="text-xs text-zinc-500">{file.id}</p>
                </div>
              </td>
              <td className="px-4 py-3 align-top">
                <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${getStatusTone(file.status)}`}>
                  {file.status.replaceAll("_", " ")}
                </span>
              </td>
              <td className="px-4 py-3 align-top">{file.payer_name_raw ?? "Pending extraction"}</td>
              <td className="px-4 py-3 align-top">{new Date(file.created_at).toLocaleString()}</td>
              <td className="px-4 py-3 align-top">
                <Link
                  href={`/era/${file.id}`}
                  className="inline-flex rounded-md border border-zinc-700 px-3 py-2 text-white transition hover:border-white"
                >
                  Open lab
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EraUploadForm() {
  const [state, setState] = useState<UploadState>(INITIAL_STATE);
  const [recentFiles, setRecentFiles] = useState<EraFileResponse[]>([]);
  const [recentFilesStatus, setRecentFilesStatus] = useState<"idle" | "loading" | "error">("loading");
  const [recentFilesError, setRecentFilesError] = useState<string | null>(null);

  async function loadRecentFiles(showLoading = false) {
    if (showLoading) {
      setRecentFilesStatus("loading");
      setRecentFilesError(null);
    }

    try {
      const response = await fetch("/api/era", {
        cache: "no-store",
      });
      const payload = (await response.json()) as EraFileResponse[] | ProcessErrorResponse;
      if (!response.ok || !Array.isArray(payload)) {
        setRecentFilesStatus("error");
        setRecentFilesError(`Unable to load recent ERA files (status ${response.status}).`);
        return;
      }
      setRecentFiles(payload.slice(0, 12));
      setRecentFilesStatus("idle");
    } catch {
      setRecentFilesStatus("error");
      setRecentFilesError("Unable to load recent ERA files right now.");
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function loadInitialRecentFiles() {
      try {
        const response = await fetch("/api/era", {
          cache: "no-store",
        });
        const payload = (await response.json()) as EraFileResponse[] | ProcessErrorResponse;
        if (cancelled) {
          return;
        }
        if (!response.ok || !Array.isArray(payload)) {
          setRecentFilesStatus("error");
          setRecentFilesError(`Unable to load recent ERA files (status ${response.status}).`);
          return;
        }
        setRecentFiles(payload.slice(0, 12));
        setRecentFilesStatus("idle");
      } catch {
        if (cancelled) {
          return;
        }
        setRecentFilesStatus("error");
        setRecentFilesError("Unable to load recent ERA files right now.");
      }
    }

    void loadInitialRecentFiles();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = event.currentTarget;
    const formData = new FormData(form);
    const file = formData.get("files");

    if (!(file instanceof File) || !file.name) {
      setState({
        status: "error",
        message: "Select an ERA file before submitting.",
        uploadedFile: null,
        processedFile: null,
        report: null,
        reportMessage: null,
        processError: null,
        payload: null,
      });
      return;
    }

    setState({
      status: "submitting",
      message: "Uploading and processing ERA file...",
      uploadedFile: null,
      processedFile: null,
      report: null,
      reportMessage: null,
      processError: null,
      payload: null,
    });

    try {
      const uploadResponse = await fetch("/api/era", {
        method: "POST",
        body: formData,
      });

      const uploadPayload = (await uploadResponse.json()) as EraFileResponse[] | ProcessErrorResponse;
      if (!uploadResponse.ok) {
        setState({
          status: "error",
          message: `Upload failed with status ${uploadResponse.status}.`,
          uploadedFile: null,
          processedFile: null,
          report: null,
          reportMessage: null,
          processError: null,
          payload: uploadPayload,
        });
        return;
      }

      const [uploadedFile] = uploadPayload as EraFileResponse[];
      if (!uploadedFile) {
        setState({
          status: "error",
          message: "Upload succeeded but no ERA file was returned.",
          uploadedFile: null,
          processedFile: null,
          report: null,
          reportMessage: null,
          processError: null,
          payload: uploadPayload,
        });
        return;
      }

      const processResponse = await fetch(`/api/era/${uploadedFile.id}/process`, {
        method: "POST",
      });
      const processPayload = (await processResponse.json()) as EraFileResponse | ProcessErrorResponse;
      let report: EraReportResponse | null = null;
      let reportMessage: string | null = null;
      let reportPayload: EraReportResponse | ProcessErrorResponse | null = null;

      if (processResponse.ok) {
        const reportResponse = await fetch(`/api/era/${uploadedFile.id}/report`);
        reportPayload = (await reportResponse.json()) as EraReportResponse | ProcessErrorResponse;
        if (reportResponse.ok) {
          report = reportPayload as EraReportResponse;
        } else if (reportResponse.status === 404) {
          reportMessage = "Processing completed, but the results report is still being prepared. Try again in a few seconds.";
        } else {
          reportMessage = `Processing completed, but the results report could not be loaded (status ${reportResponse.status}).`;
        }
      }

      setState({
        status: processResponse.ok ? "success" : "error",
        message: processResponse.ok
          ? report
            ? "Upload and processing completed. Results are ready below."
            : "Upload and processing completed."
          : "Upload completed, but processing needs attention.",
        uploadedFile,
        processedFile: processResponse.ok ? (processPayload as EraFileResponse) : null,
        report,
        reportMessage,
        processError: processResponse.ok ? null : formatProcessError(processPayload as ProcessErrorResponse, processResponse.status),
        payload: report ?? reportPayload ?? processPayload,
      });

      await loadRecentFiles(false);
      form.reset();
    } catch (error) {
      setState({
        status: "error",
        message:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to submit the ERA upload right now.",
        uploadedFile: null,
        processedFile: null,
        report: null,
        reportMessage: null,
        processError: null,
        payload: null,
      });
    }
  }

  return (
    <div className="space-y-4">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label htmlFor="era-file" className="block text-sm font-medium text-zinc-200">
            ERA PDF
          </label>
          <input
            id="era-file"
            name="files"
            type="file"
            accept="application/pdf,.pdf"
            required
            className="block w-full rounded-md border border-zinc-700 bg-black/50 px-3 py-2 text-zinc-200 file:mr-4 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-2 file:text-sm file:font-medium file:text-black"
          />
        </div>

        <button
          type="submit"
          disabled={state.status === "submitting"}
          className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:border-zinc-700 disabled:text-zinc-500"
        >
          {state.status === "submitting" ? "Uploading..." : "Upload ERA"}
        </button>
      </form>

      {state.message ? (
        <p
          className={
            state.status === "error"
              ? "rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200"
              : "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-emerald-200"
          }
        >
          {state.message}
        </p>
      ) : null}

      {state.uploadedFile ? <ResultCard label="Upload result" file={state.uploadedFile} /> : null}

      {state.processedFile ? <ResultCard label="Processing result" file={state.processedFile} /> : null}

      {state.report ? <ReviewCard report={state.report} /> : null}

      {state.processedFile ? (
        <div className="flex flex-wrap gap-3">
          <Link
            href={`/era/${state.processedFile.id}`}
            className="inline-flex rounded-md border border-white px-4 py-2 text-sm font-medium text-white transition hover:bg-white hover:text-black"
          >
            Open ERA lab
          </Link>
        </div>
      ) : null}

      {state.reportMessage ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
          {state.reportMessage}
        </div>
      ) : null}

      {state.processError ? (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-rose-200">
          {state.processError}
        </div>
      ) : null}

      {state.payload ? (
        <details className="rounded-lg border border-zinc-800 bg-black/40 p-4 text-zinc-300">
          <summary className="cursor-pointer text-sm font-medium text-white">Raw API response</summary>
          <pre className="mt-4 overflow-x-auto text-xs text-zinc-200">
            {JSON.stringify(state.payload, null, 2)}
          </pre>
        </details>
      ) : null}

      <div className="space-y-3 rounded-xl border border-zinc-800 bg-black/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Recent ERA files</p>
            <p className="mt-2 text-sm text-zinc-400">
              Jump straight into the file-level lab without uploading the same PDF again.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              void loadRecentFiles(true);
            }}
            className="inline-flex rounded-md border border-zinc-700 px-3 py-2 text-white transition hover:border-white"
          >
            Refresh list
          </button>
        </div>

        {recentFilesError ? (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
            {recentFilesError}
          </div>
        ) : null}

        {recentFilesStatus === "loading" && recentFiles.length === 0 ? (
          <div className="h-24 animate-pulse rounded-xl border border-zinc-800 bg-zinc-950/40" />
        ) : (
          <RecentEraFilesCard files={recentFiles} />
        )}
      </div>
    </div>
  );
}

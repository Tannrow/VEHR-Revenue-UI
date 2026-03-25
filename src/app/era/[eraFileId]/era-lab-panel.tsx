"use client";

import { useEffect, useState } from "react";

import { apiClientFetch } from "@/lib/api/client";

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
};

type EraDebugLogResponse = {
  created_at: string;
  stage: string;
  message: string;
};

type EraDebugRowCountsResponse = {
  extract_results: number;
  structured_results: number;
  claim_lines: number;
  work_items: number;
  validation_reports: number;
};

type EraProcessDiagnosticsResponse = {
  era_file_id: string;
  current_status: string;
  current_stage: string | null;
  stage_started_at: string | null;
  stage_completed_at: string | null;
  retry_required: boolean;
  has_extract_result: boolean;
  has_structured_result: boolean;
  finalized: boolean | null;
  last_error_code: string | null;
  last_error_stage: string | null;
};

type EraDebugFileResponse = {
  id: string;
  status: string;
  sha256: string;
  created_at: string;
  updated_at: string;
  error_detail_safe_json: Record<string, unknown> | null;
  finalized_at: string | null;
  processing_version: string | null;
};

type EraLabPagePreviewResponse = {
  page_number: number;
  line_count: number;
  table_count: number;
  lines_preview: string[];
  tables_preview: Array<{
    row_count: number;
    rows_preview: string[][];
  }>;
};

type EraLabLineResponse = {
  line_index: number | null;
  claim_ref: string;
  service_date: string | null;
  proc_code: string | null;
  charge_cents: number | null;
  allowed_cents: number | null;
  paid_cents: number | null;
  patient_responsibility_cents: number | null;
  adjustments: Array<{
    code: string | null;
    amount_cents: number;
  }>;
  match_status: string;
  source_provenance: string[];
  confidence_band: string | null;
  unresolved_fields: string[];
  conflict_fields: string[];
  review_required: boolean;
};

type EraLabPreviewWorkItemResponse = {
  claim_ref: string;
  type: string;
  payer_name: string;
  dollars_cents: number;
  status: string;
  line_index: number;
};

type EraLabResponse = {
  era_file: EraDebugFileResponse;
  diagnostics: EraProcessDiagnosticsResponse;
  persisted_report: EraReportResponse | null;
  latest_processing_logs: EraDebugLogResponse[];
  row_counts: EraDebugRowCountsResponse;
  extract_artifact: {
    available: boolean;
    extractor: string | null;
    model_id: string | null;
    extracted_at: string | null;
    page_count: number;
    table_count: number;
    ocr_line_count: number;
    llm_input_pages: EraLabPagePreviewResponse[];
    deterministic_rows: EraLabLineResponse[];
  } | null;
  structuring_artifact: {
    available: boolean;
    llm: string | null;
    deployment: string | null;
    api_version: string | null;
    prompt_version: string | null;
    created_at: string | null;
    payer_name: string | null;
    received_date: string | null;
    declared_totals_cents: {
      paid: number;
      adjustment: number;
      patient_responsibility: number;
      net: number;
    } | null;
    diagnostics: {
      deterministic_row_count: number;
      llm_row_count: number;
      merged_row_count: number;
      deterministic_only_row_count: number;
      llm_only_row_count: number;
      conflict_count: number;
      review_required_count: number;
      low_confidence_count: number;
      critical_missing_count: number;
      llm_retry_count: number;
      llm_duration_ms: number;
      llm_request_id: string | null;
    } | null;
    claim_lines: EraLabLineResponse[];
  } | null;
  normalized_preview: {
    report: {
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
      top_work_items: EraLabPreviewWorkItemResponse[];
    };
    work_items: EraLabPreviewWorkItemResponse[];
  } | null;
  replay: {
    mode: string;
    preview_only: boolean;
    used_cached_extract: boolean;
    used_cached_structured: boolean;
    ran_document_intelligence: boolean;
    ran_structuring: boolean;
    request_id: string;
    document_intelligence_request_id: string | null;
    document_intelligence_retry_count: number;
    document_intelligence_duration_ms: number;
    openai_request_id: string | null;
    openai_retry_count: number;
    openai_duration_ms: number;
  } | null;
  available_replay_modes: string[];
};

type ReplayMode = "cached" | "rerun_structuring" | "rerun_extract";

type LabState = {
  status: "loading" | "ready" | "error" | "replaying";
  snapshot: EraLabResponse | null;
  error: string | null;
  activeReplayMode: ReplayMode | null;
};

const INITIAL_STATE: LabState = {
  status: "loading",
  snapshot: null,
  error: null,
  activeReplayMode: null,
};

function formatCents(value: number | null | undefined): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format((value ?? 0) / 100);
}

function getBadgeTone(tone: "healthy" | "warning" | "error" | "neutral"): string {
  switch (tone) {
    case "healthy":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-200";
    case "error":
      return "border-rose-500/40 bg-rose-500/10 text-rose-200";
    case "neutral":
    default:
      return "border-zinc-700 bg-black/30 text-zinc-300";
  }
}

function statusTone(status: string): "healthy" | "warning" | "error" {
  if (status === "COMPLETE" || status === "MATCHED" || status === "HIGH") {
    return "healthy";
  }
  if (status === "ERROR" || status === "LOW") {
    return "error";
  }
  return "warning";
}

function StatusBadge({ label, tone }: { label: string; tone: "healthy" | "warning" | "error" | "neutral" }) {
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${getBadgeTone(tone)}`}>
      {label}
    </span>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "healthy" | "warning" | "error" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">{label}</p>
      <div className="mt-3 flex items-start justify-between gap-3">
        <p className="text-lg font-semibold text-white break-all">{value}</p>
        <StatusBadge label={label} tone={tone} />
      </div>
      {detail ? <p className="mt-3 text-sm text-zinc-400">{detail}</p> : null}
    </div>
  );
}

function LineTable({ lines }: { lines: EraLabLineResponse[] }) {
  if (lines.length === 0) {
    return <p className="text-sm text-zinc-400">No merged claim lines are available for this snapshot.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
        <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">Claim</th>
            <th className="px-4 py-3 font-medium">Service</th>
            <th className="px-4 py-3 font-medium">Proc</th>
            <th className="px-4 py-3 font-medium">Paid</th>
            <th className="px-4 py-3 font-medium">Confidence</th>
            <th className="px-4 py-3 font-medium">Sources</th>
            <th className="px-4 py-3 font-medium">Review</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-950/40 text-zinc-200">
          {lines.map((line, index) => (
            <tr key={`${line.claim_ref}-${line.proc_code ?? "na"}-${index}`}>
              <td className="px-4 py-3 align-top">
                <div className="space-y-2">
                  <p className="font-medium text-white">{line.claim_ref}</p>
                  {line.line_index !== null ? <p className="text-xs text-zinc-500">Line {line.line_index + 1}</p> : null}
                </div>
              </td>
              <td className="px-4 py-3 align-top">{line.service_date ?? "Unknown"}</td>
              <td className="px-4 py-3 align-top">{line.proc_code ?? "Unknown"}</td>
              <td className="px-4 py-3 align-top">{formatCents(line.paid_cents)}</td>
              <td className="px-4 py-3 align-top">
                <StatusBadge
                  label={line.confidence_band ?? "Unknown"}
                  tone={line.confidence_band ? statusTone(line.confidence_band) : "neutral"}
                />
              </td>
              <td className="px-4 py-3 align-top">
                <div className="flex flex-wrap gap-2">
                  {line.source_provenance.length > 0 ? (
                    line.source_provenance.map((source) => (
                      <span key={source} className="rounded-full border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300">
                        {source}
                      </span>
                    ))
                  ) : (
                    <span className="text-zinc-500">Unknown</span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3 align-top">
                <div className="space-y-2">
                  <StatusBadge label={line.review_required ? "Needs review" : "Clean"} tone={line.review_required ? "warning" : "healthy"} />
                  {line.conflict_fields.length > 0 ? (
                    <p className="text-xs text-amber-200">Conflicts: {line.conflict_fields.join(", ")}</p>
                  ) : null}
                  {line.unresolved_fields.length > 0 ? (
                    <p className="text-xs text-amber-200">Missing: {line.unresolved_fields.join(", ")}</p>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkItemTable({ items }: { items: EraLabPreviewWorkItemResponse[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-zinc-400">No work items were generated for this preview.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
        <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">Claim</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Amount</th>
            <th className="px-4 py-3 font-medium">Line</th>
            <th className="px-4 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-950/40 text-zinc-200">
          {items.map((item) => (
            <tr key={`${item.claim_ref}-${item.type}`}>
              <td className="px-4 py-3 align-top text-white">{item.claim_ref}</td>
              <td className="px-4 py-3 align-top">{item.type}</td>
              <td className="px-4 py-3 align-top">{formatCents(item.dollars_cents)}</td>
              <td className="px-4 py-3 align-top">{item.line_index + 1}</td>
              <td className="px-4 py-3 align-top">{item.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExtractPreview({ pages }: { pages: EraLabPagePreviewResponse[] }) {
  if (pages.length === 0) {
    return <p className="text-sm text-zinc-400">No redacted layout preview is available for this snapshot.</p>;
  }

  return (
    <div className="space-y-3">
      {pages.map((page) => (
        <details key={page.page_number} className="rounded-xl border border-zinc-800 bg-black/30 p-4">
          <summary className="cursor-pointer text-sm font-medium text-white">
            Page {page.page_number} • {page.line_count} lines • {page.table_count} tables
          </summary>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Redacted line preview</p>
              <ul className="space-y-2 text-sm text-zinc-300">
                {page.lines_preview.map((line, index) => (
                  <li key={`${page.page_number}-line-${index}`} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2">
                    {line}
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Table preview</p>
              <div className="space-y-3">
                {page.tables_preview.map((table, index) => (
                  <div key={`${page.page_number}-table-${index}`} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
                    <p className="text-xs text-zinc-500">Rows detected: {table.row_count}</p>
                    <div className="mt-2 space-y-2 text-xs text-zinc-300">
                      {table.rows_preview.map((row, rowIndex) => (
                        <div key={`${page.page_number}-table-${index}-row-${rowIndex}`} className="rounded border border-zinc-800 px-2 py-1">
                          {row.join(" | ")}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

export function EraLabPanel({ eraFileId }: { eraFileId: string }) {
  const [state, setState] = useState<LabState>(INITIAL_STATE);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const response = await apiClientFetch(`/api/era/${eraFileId}/lab`);
      if (cancelled) {
        return;
      }

      if (!response.ok || !response.data || typeof response.data !== "object") {
        setState({
          status: "error",
          snapshot: null,
          error: response.text.trim() || `Unable to load the ERA lab snapshot (status ${response.status}).`,
          activeReplayMode: null,
        });
        return;
      }

      setState({
        status: "ready",
        snapshot: response.data as EraLabResponse,
        error: null,
        activeReplayMode: null,
      });
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [eraFileId]);

  async function runReplay(mode: ReplayMode) {
    setState((current) => ({
      status: "replaying",
      snapshot: current.snapshot,
      error: null,
      activeReplayMode: mode,
    }));

    const response = await apiClientFetch(`/api/era/${eraFileId}/replay`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ mode }),
    });

    if (!response.ok || !response.data || typeof response.data !== "object") {
      setState((current) => ({
        status: "error",
        snapshot: current.snapshot,
        error: response.text.trim() || `Replay preview failed with status ${response.status}.`,
        activeReplayMode: null,
      }));
      return;
    }

    setState({
      status: "ready",
      snapshot: response.data as EraLabResponse,
      error: null,
      activeReplayMode: null,
    });
  }

  if (state.status === "loading" && state.snapshot === null) {
    return <div className="h-72 animate-pulse rounded-xl border border-zinc-800 bg-zinc-950/40" />;
  }

  if (state.snapshot === null) {
    return (
      <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-rose-200">
        {state.error ?? "Unable to load the ERA lab snapshot."}
      </div>
    );
  }

  const { snapshot } = state;
  const persistedReport = snapshot.persisted_report;
  const previewReport = snapshot.normalized_preview?.report ?? null;
  const structuringDiagnostics = snapshot.structuring_artifact?.diagnostics ?? null;

  return (
    <div className="space-y-6 text-sm text-zinc-300">
      {state.error ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
          {state.error}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="File status"
          value={snapshot.era_file.status.replaceAll("_", " ")}
          detail={snapshot.diagnostics.current_stage ? `Current stage: ${snapshot.diagnostics.current_stage}` : "No active stage."}
          tone={statusTone(snapshot.era_file.status)}
        />
        <SummaryCard
          label="Persisted report"
          value={persistedReport ? (persistedReport.finalized ? "Finalized" : "Needs review") : "Not available"}
          detail={
            persistedReport
              ? `${persistedReport.claim_count} claims, ${persistedReport.work_item_count} work items`
              : "The backend has not persisted a validation report yet."
          }
          tone={persistedReport ? (persistedReport.finalized ? "healthy" : "warning") : "neutral"}
        />
        <SummaryCard
          label="Replay preview"
          value={snapshot.replay ? snapshot.replay.mode.replaceAll("_", " ") : "Persisted snapshot"}
          detail={
            snapshot.replay
              ? `Preview-only. Cached extract: ${snapshot.replay.used_cached_extract ? "yes" : "no"}, cached structured: ${snapshot.replay.used_cached_structured ? "yes" : "no"}.`
              : "No replay preview has been run yet."
          }
          tone={snapshot.replay ? "warning" : "neutral"}
        />
        <SummaryCard
          label="Processing version"
          value={snapshot.era_file.processing_version ?? "Unknown"}
          detail={`SHA-256: ${snapshot.era_file.sha256}`}
          tone="neutral"
        />
      </div>

      <div className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Replay controls</h2>
            <p className="max-w-3xl text-sm text-slate-400">
              Re-run selected stages against the stored PDF without mutating persisted claim lines, work items, or reports.
            </p>
          </div>
          {snapshot.replay ? <StatusBadge label="Preview only" tone="warning" /> : null}
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => {
              void runReplay("cached");
            }}
            disabled={state.status === "replaying"}
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white disabled:cursor-not-allowed disabled:text-zinc-500"
          >
            {state.activeReplayMode === "cached" ? "Running cached preview..." : "Use cached artifacts"}
          </button>
          <button
            type="button"
            onClick={() => {
              void runReplay("rerun_structuring");
            }}
            disabled={state.status === "replaying"}
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white disabled:cursor-not-allowed disabled:text-zinc-500"
          >
            {state.activeReplayMode === "rerun_structuring" ? "Rerunning structuring..." : "Rerun structuring"}
          </button>
          <button
            type="button"
            onClick={() => {
              void runReplay("rerun_extract");
            }}
            disabled={state.status === "replaying"}
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white disabled:cursor-not-allowed disabled:text-zinc-500"
          >
            {state.activeReplayMode === "rerun_extract" ? "Rerunning extraction..." : "Rerun Document Intelligence"}
          </button>
        </div>

        {snapshot.replay ? (
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Document Intelligence</p>
              <p className="mt-3 text-white">
                {snapshot.replay.ran_document_intelligence ? "Reran live" : snapshot.replay.used_cached_extract ? "Used cached extract" : "Not used"}
              </p>
              <p className="mt-2 text-xs text-zinc-500">
                Retry count: {snapshot.replay.document_intelligence_retry_count} • Duration: {snapshot.replay.document_intelligence_duration_ms} ms
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Azure OpenAI</p>
              <p className="mt-3 text-white">
                {snapshot.replay.ran_structuring ? "Reran live" : snapshot.replay.used_cached_structured ? "Used cached structured result" : "Not used"}
              </p>
              <p className="mt-2 text-xs text-zinc-500">
                Retry count: {snapshot.replay.openai_retry_count} • Duration: {snapshot.replay.openai_duration_ms} ms
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Replay request</p>
              <p className="mt-3 break-all text-white">{snapshot.replay.request_id}</p>
              <p className="mt-2 text-xs text-zinc-500">Persisted rows and reports stay untouched.</p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-6">
          <div className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
            <div className="mb-5 space-y-1">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Document Intelligence extract</h2>
              <p className="text-sm text-slate-400">
                Redacted line and table previews from the compact layout sent downstream for structuring.
              </p>
            </div>

            {snapshot.extract_artifact ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <SummaryCard
                    label="Pages"
                    value={String(snapshot.extract_artifact.page_count)}
                    detail={`${snapshot.extract_artifact.ocr_line_count} OCR lines`}
                  />
                  <SummaryCard
                    label="Tables"
                    value={String(snapshot.extract_artifact.table_count)}
                    detail={snapshot.extract_artifact.model_id ?? "Unknown model"}
                  />
                  <SummaryCard
                    label="Deterministic rows"
                    value={String(snapshot.extract_artifact.deterministic_rows.length)}
                    detail={snapshot.extract_artifact.extractor ?? "azure_doc_intelligence"}
                  />
                </div>
                <ExtractPreview pages={snapshot.extract_artifact.llm_input_pages} />
              </div>
            ) : (
              <p className="text-sm text-zinc-400">This file does not have an extract artifact yet.</p>
            )}
          </div>

          <div className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
            <div className="mb-5 space-y-1">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Merged claim lines</h2>
              <p className="text-sm text-slate-400">
                Deterministic table parsing stays primary. Azure OpenAI fills weak fields and disagreements are surfaced instead of hidden.
              </p>
            </div>

            {snapshot.structuring_artifact ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <SummaryCard
                    label="Payer"
                    value={snapshot.structuring_artifact.payer_name ?? "Unknown"}
                    detail={snapshot.structuring_artifact.received_date ?? "No received date"}
                  />
                  <SummaryCard
                    label="Rows"
                    value={String(structuringDiagnostics?.merged_row_count ?? 0)}
                    detail={`Deterministic ${structuringDiagnostics?.deterministic_row_count ?? 0} • LLM ${structuringDiagnostics?.llm_row_count ?? 0}`}
                  />
                  <SummaryCard
                    label="Conflicts"
                    value={String(structuringDiagnostics?.conflict_count ?? 0)}
                    detail={`Low confidence ${structuringDiagnostics?.low_confidence_count ?? 0}`}
                    tone={(structuringDiagnostics?.conflict_count ?? 0) > 0 ? "warning" : "healthy"}
                  />
                </div>
                <LineTable lines={snapshot.structuring_artifact.claim_lines} />
              </div>
            ) : (
              <p className="text-sm text-zinc-400">This file does not have a structuring artifact yet.</p>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
            <div className="mb-5 space-y-1">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Normalization and review</h2>
              <p className="text-sm text-slate-400">
                Preview of the work items and validation outcome the current snapshot would produce.
              </p>
            </div>

            {previewReport ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <SummaryCard
                    label="Preview finalization"
                    value={previewReport.finalized ? "Finalized" : "Needs review"}
                    detail={`Reconciled: ${previewReport.reconciled ? "yes" : "no"}`}
                    tone={previewReport.finalized ? "healthy" : "warning"}
                  />
                  <SummaryCard
                    label="Preview totals"
                    value={formatCents(previewReport.net_cents)}
                    detail={`Paid ${formatCents(previewReport.total_paid_cents)} • Adjustments ${formatCents(previewReport.total_adjustment_cents)}`}
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <StatusBadge label={`Conflicts ${previewReport.conflict_count}`} tone={previewReport.conflict_count > 0 ? "warning" : "healthy"} />
                  <StatusBadge label={`Review rows ${previewReport.review_required_count}`} tone={previewReport.review_required_count > 0 ? "warning" : "healthy"} />
                  <StatusBadge label={`Critical missing ${previewReport.critical_missing_count}`} tone={previewReport.critical_missing_count > 0 ? "warning" : "healthy"} />
                  <StatusBadge label={`PHI scan ${previewReport.phi_scan_passed ? "passed" : "attention"}`} tone={previewReport.phi_scan_passed ? "healthy" : "warning"} />
                </div>

                <WorkItemTable items={snapshot.normalized_preview?.work_items ?? []} />
              </div>
            ) : (
              <p className="text-sm text-zinc-400">A normalization preview is not available yet.</p>
            )}
          </div>

          <div className="rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.94),rgba(17,20,28,0.96))] p-5 shadow-[0_18px_70px_rgba(0,0,0,0.22)] backdrop-blur-sm md:p-6">
            <div className="mb-5 space-y-1">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Processing trail</h2>
              <p className="text-sm text-slate-400">
                Safe processing logs and row counts for this file. No raw OCR or PHI-bearing payloads are emitted here.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Row counts</p>
                <dl className="mt-3 space-y-2 text-sm text-zinc-300">
                  <div className="flex items-center justify-between gap-3">
                    <dt>Extract results</dt>
                    <dd className="text-white">{snapshot.row_counts.extract_results}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Structured results</dt>
                    <dd className="text-white">{snapshot.row_counts.structured_results}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Claim lines</dt>
                    <dd className="text-white">{snapshot.row_counts.claim_lines}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Work items</dt>
                    <dd className="text-white">{snapshot.row_counts.work_items}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Validation reports</dt>
                    <dd className="text-white">{snapshot.row_counts.validation_reports}</dd>
                  </div>
                </dl>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Last error</p>
                <div className="mt-3 space-y-2 text-sm text-zinc-300">
                  <p>Code: <span className="text-white">{snapshot.diagnostics.last_error_code ?? "None"}</span></p>
                  <p>Stage: <span className="text-white">{snapshot.diagnostics.last_error_stage ?? "None"}</span></p>
                  <p>Retry required: <span className="text-white">{snapshot.diagnostics.retry_required ? "Yes" : "No"}</span></p>
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {snapshot.latest_processing_logs.map((entry, index) => (
                <div key={`${entry.created_at}-${entry.stage}-${index}`} className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <StatusBadge label={entry.stage} tone="neutral" />
                    <p className="text-xs text-zinc-500">{new Date(entry.created_at).toLocaleString()}</p>
                  </div>
                  <p className="mt-3 break-words text-sm text-zinc-300">{entry.message}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <details className="rounded-xl border border-zinc-800 bg-black/40 p-4">
        <summary className="cursor-pointer text-sm font-medium text-white">Raw lab snapshot</summary>
        <pre className="mt-4 overflow-x-auto text-xs text-zinc-200">{JSON.stringify(snapshot, null, 2)}</pre>
      </details>
    </div>
  );
}

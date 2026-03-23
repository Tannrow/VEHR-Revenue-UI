"use client";

import { useState } from "react";

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
  processError: string | null;
  payload: EraFileResponse | EraFileResponse[] | ProcessErrorResponse | null;
};

const INITIAL_STATE: UploadState = {
  status: "idle",
  message: null,
  uploadedFile: null,
  processedFile: null,
  processError: null,
  payload: null,
};

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

export function EraUploadForm() {
  const [state, setState] = useState<UploadState>(INITIAL_STATE);

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
          processError: null,
          payload: uploadPayload,
        });
        return;
      }

      const processResponse = await fetch(`/api/era/${uploadedFile.id}/process`, {
        method: "POST",
      });
      const processPayload = (await processResponse.json()) as EraFileResponse | ProcessErrorResponse;

      setState({
        status: processResponse.ok ? "success" : "error",
        message: processResponse.ok
          ? "Upload and processing completed."
          : "Upload completed, but processing needs attention.",
        uploadedFile,
        processedFile: processResponse.ok ? (processPayload as EraFileResponse) : null,
        processError: processResponse.ok ? null : formatProcessError(processPayload as ProcessErrorResponse, processResponse.status),
        payload: processPayload,
      });

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
    </div>
  );
}

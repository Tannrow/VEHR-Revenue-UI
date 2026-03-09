import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { fetchInternal } from "@/lib/internal-api";

export const dynamic = "force-dynamic";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
type JsonRecord = { [key: string]: JsonValue };

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatErrorMessage(status: number, payload: unknown, text: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return isFetchFailedMessage(payload) ? "Unable to reach the VEHR claims endpoint right now." : payload.trim();
  }

  if (isRecord(payload)) {
    const errorMessage = payload.error;
    const detailMessage = payload.detail;
    const message = typeof errorMessage === "string" ? errorMessage : detailMessage;

    if (typeof message === "string" && message.trim()) {
      return isFetchFailedMessage(message) ? "Unable to reach the VEHR claims endpoint right now." : message.trim();
    }
  }

  if (text.trim()) {
    return isFetchFailedMessage(text) ? "Unable to reach the VEHR claims endpoint right now." : text.trim();
  }

  if (status === 401 || status === 403) {
    return `Backend authorization failed with status ${status}.`;
  }

  return `Unable to load claims (status ${status}).`;
}

async function getClaimsState(): Promise<{ payload: unknown; error: string | null }> {
  try {
    const response = await fetchInternal("/api/claims");

    if (!response.ok) {
      return {
        payload: null,
        error: formatErrorMessage(response.status, response.data, response.text),
      };
    }

    return {
      payload: response.data ?? response.text,
      error: null,
    };
  } catch (error) {
    return {
      payload: null,
      error:
        error instanceof Error && !isFetchFailedMessage(error.message)
          ? error.message
          : "Unable to load claims right now.",
    };
  }
}

function getColumns(records: JsonRecord[]): string[] {
  return Array.from(new Set(records.flatMap((record) => Object.keys(record))));
}

function renderCellValue(value: unknown): string {
  if (value === undefined) {
    return "";
  }

  if (Array.isArray(value) || isRecord(value)) {
    return safeJson(value);
  }

  return value === null || value === undefined ? "" : String(value);
}

export default async function ClaimsPage() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        title="Claims"
        description="Claims data is loaded through the UI's same-origin proxy route."
        footer="Claims data is served from /api/claims via the UI origin."
      >
        <SignInRequiredCard resource="claims" />
      </PageShell>
    );
  }

  const { payload, error } = await getClaimsState();
  const arrayPayload = Array.isArray(payload) ? payload : [];
  const isArrayPayload = Array.isArray(payload);
  const canRenderRecordTable = isArrayPayload && arrayPayload.every(isRecord);
  const rows = canRenderRecordTable ? arrayPayload : [];
  const columns = rows.length > 0 ? getColumns(rows) : [];

  return (
    <PageShell
      title="Claims"
      description="Claims data is loaded through the UI's same-origin proxy route."
      footer="Claims data is served from /api/claims via the UI origin."
    >
      <SectionCard title="Claims data">
        <div className="space-y-6 text-sm text-zinc-300">
          {error ? (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
              {error}
            </div>
          ) : null}

          {!error && canRenderRecordTable && columns.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="min-w-full divide-y divide-zinc-800 text-left">
                <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    {columns.map((column) => (
                      <th key={column} className="px-4 py-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-950/40">
                  {rows.map((row, index) => (
                    <tr key={String(row.claim_id ?? row.id ?? index)}>
                      {columns.map((column) => (
                        <td key={column} className="px-4 py-3 align-top text-zinc-200">
                          {renderCellValue(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {!error && isArrayPayload && arrayPayload.length === 0 ? (
            <div className="rounded-md border border-zinc-800 bg-black/40 px-4 py-3 text-zinc-300">
              No claims were returned.
            </div>
          ) : null}

          {!error && isArrayPayload && arrayPayload.length > 0 && !canRenderRecordTable ? (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="min-w-full divide-y divide-zinc-800 text-left">
                <thead className="bg-black/40 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-950/40">
                  {arrayPayload.map((value, index) => (
                    <tr key={index}>
                      <td className="px-4 py-3 align-top text-zinc-200">{safeJson(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {!error && !isArrayPayload ? (
            <div className="rounded-md border border-zinc-800 bg-black/40 p-4">
              <p className="mb-3 text-zinc-300">Claims response</p>
              <pre className="overflow-x-auto text-xs text-zinc-400">{safeJson(payload ?? null)}</pre>
            </div>
          ) : null}

          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Back to home
          </Link>
        </div>
      </SectionCard>
    </PageShell>
  );
}

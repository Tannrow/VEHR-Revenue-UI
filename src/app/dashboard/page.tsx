import type { ReactNode } from "react";
import Link from "next/link";

import { PageShell, SectionCard } from "@/components/page-shell";
import { SignInRequiredCard } from "@/components/sign-in-required-card";
import { getAccessToken } from "@/lib/auth";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { fetchInternal } from "@/lib/internal-api";

export const dynamic = "force-dynamic";

const DASHBOARD_FIELDS = [
  "snapshot_id",
  "generated_at",
  "total_exposure_cents",
  "expected_recovery_30_day_cents",
  "short_term_cash_opportunity_cents",
  "high_risk_claim_count",
  "critical_pre_submission_count",
  "top_aggressive_payers",
  "top_revenue_loss_drivers",
  "top_worklist",
] as const;

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
    return isFetchFailedMessage(payload) ? "Unable to reach the VEHR dashboard right now." : payload.trim();
  }

  if (isRecord(payload)) {
    const errorMessage = payload.error;
    const detailMessage = payload.detail;
    const message = typeof errorMessage === "string" ? errorMessage : detailMessage;

    if (typeof message === "string" && message.trim()) {
      return isFetchFailedMessage(message) ? "Unable to reach the VEHR dashboard right now." : message.trim();
    }
  }

  if (text.trim()) {
    return isFetchFailedMessage(text) ? "Unable to reach the VEHR dashboard right now." : text.trim();
  }

  if (status === 401 || status === 403) {
    return `Backend authorization failed with status ${status}.`;
  }

  return `Unable to load dashboard data (status ${status}).`;
}

async function getDashboardState(): Promise<{ payload: JsonRecord | null; error: string | null }> {
  try {
    const response = await fetchInternal("/api/dashboard");

    if (!response.ok) {
      return {
        payload: null,
        error: formatErrorMessage(response.status, response.data, response.text),
      };
    }

    return {
      payload: isRecord(response.data) ? response.data : null,
      error: null,
    };
  } catch (error) {
    return {
      payload: null,
      error:
        error instanceof Error && !isFetchFailedMessage(error.message)
          ? error.message
          : "Unable to load dashboard data right now.",
    };
  }
}

function renderFieldValue(value: JsonValue): ReactNode {
  if (Array.isArray(value) || isRecord(value)) {
    return (
      <pre className="mt-2 overflow-x-auto rounded-md bg-black/40 p-3 text-xs text-zinc-200">
        {safeJson(value)}
      </pre>
    );
  }

  return <p className="mt-2 text-lg font-semibold text-white">{value === null ? "null" : String(value)}</p>;
}

export default async function DashboardPage() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return (
      <PageShell
        title="Dashboard"
        description="Live revenue snapshot data is loaded through the UI's same-origin proxy route."
        footer="Dashboard data is served from /api/dashboard via the UI origin."
      >
        <SignInRequiredCard resource="the dashboard" />
      </PageShell>
    );
  }

  const { payload, error } = await getDashboardState();
  const fields = payload
    ? DASHBOARD_FIELDS.filter((field) => field in payload).map((field) => [field, payload[field]] as const)
    : [];

  return (
    <PageShell
      title="Dashboard"
      description="Live revenue snapshot data is loaded through the UI's same-origin proxy route."
      footer="Dashboard data is served from /api/dashboard via the UI origin."
    >
      <SectionCard title="Revenue snapshot">
        <div className="space-y-6 text-sm text-zinc-300">
          {error ? (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
              {error}
            </div>
          ) : null}

          {!error && fields.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {fields.map(([field, value]) => (
                <div key={field} className="rounded-lg border border-zinc-800 bg-black/40 p-4">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">{field}</p>
                  {renderFieldValue(value)}
                </div>
              ))}
            </div>
          ) : null}

          {!error && fields.length === 0 ? (
            <div className="rounded-md border border-zinc-800 bg-black/40 p-4">
              <p className="mb-3 text-zinc-300">No dashboard fields were returned.</p>
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

"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { SectionCard } from "@/components/page-shell";
import {
  fetchLatestRevenueSnapshotState,
  SNAPSHOT_MISSING_REFRESH_INTERVAL_MS,
  type DashboardState,
} from "@/lib/api/revenue";
import {
  assertSnapshotExists,
  safeSnapshotAccess,
  type JsonRecord,
  type JsonValue,
  type RevenueSnapshotMissing,
  type RevenueSnapshotResponse,
} from "@/lib/api/types";

const DASHBOARD_FIELDS: Array<keyof RevenueSnapshotResponse> = [
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
];

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

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {Array.from({ length: DASHBOARD_FIELDS.length }).map((_, index) => (
          <div
            key={`dashboard-skeleton-${index}`}
            className="animate-pulse rounded-lg border border-zinc-800 bg-black/40 p-4"
          >
            <div className="h-3 w-28 rounded bg-zinc-800" />
            <div className="mt-4 h-8 w-40 rounded bg-zinc-700" />
          </div>
        ))}
      </div>
      <div className="h-10 w-28 animate-pulse rounded-md border border-zinc-800 bg-black/40" />
    </div>
  );
}

function SnapshotMissingState({ detail }: { detail: RevenueSnapshotMissing }) {
  return (
    <div className="space-y-6 text-sm text-zinc-300">
      <div className="rounded-md border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sky-100">
        <p className="font-semibold text-white">Snapshot generating</p>
        <p className="mt-2">
          {detail.detail?.trim() || "The latest revenue snapshot is still being generated. We'll retry automatically every 30 seconds."}
        </p>
      </div>
      <BackHomeLink />
    </div>
  );
}

function DashboardErrorState({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-6 text-sm text-zinc-300">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
        <p className="font-semibold text-white">Dashboard unavailable</p>
        <p className="mt-2">{error}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
        >
          Retry
        </button>
        <BackHomeLink />
      </div>
    </div>
  );
}

function UnauthorizedState({ error }: { error: string }) {
  return (
    <div className="space-y-6 text-sm text-zinc-300">
      <div className="rounded-md border border-zinc-700 bg-black/40 px-4 py-3">
        <p className="font-semibold text-white">Session expired</p>
        <p className="mt-2">{error}</p>
      </div>
      <BackHomeLink />
    </div>
  );
}

function BackHomeLink() {
  return (
    <Link href="/" className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white">
      Back to home
    </Link>
  );
}

function DashboardReadyState({ snapshot }: { snapshot: RevenueSnapshotResponse }) {
  assertSnapshotExists(snapshot);

  const fields = DASHBOARD_FIELDS.flatMap((field) => {
    const value = safeSnapshotAccess(snapshot, field);

    return value === null ? [] : ([[field, value]] as const);
  });

  if (fields.length === 0) {
    return (
      <div className="space-y-6 text-sm text-zinc-300">
        <div className="rounded-md border border-zinc-800 bg-black/40 p-4">
          <p className="mb-3 text-zinc-300">No dashboard fields were returned.</p>
          <pre className="overflow-x-auto text-xs text-zinc-400">{safeJson(snapshot)}</pre>
        </div>
        <BackHomeLink />
      </div>
    );
  }

  return (
    <div className="space-y-6 text-sm text-zinc-300">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {fields.map(([field, value]) => (
          <div key={field} className="rounded-lg border border-zinc-800 bg-black/40 p-4">
            <p className="text-xs uppercase tracking-wide text-zinc-500">{field}</p>
            {renderFieldValue(value)}
          </div>
        ))}
      </div>
      <BackHomeLink />
    </div>
  );
}

function renderDashboardState(state: DashboardState, onRetry: () => void): ReactNode {
  switch (state.status) {
    case "loading":
      return <DashboardSkeleton />;
    case "snapshot_missing":
      return <SnapshotMissingState detail={state.detail} />;
    case "ready":
      return <DashboardReadyState snapshot={state.snapshot} />;
    case "unauthorized":
      return <UnauthorizedState error={state.error} />;
    case "error":
      return <DashboardErrorState error={state.error} onRetry={onRetry} />;
    default:
      return <DashboardErrorState error="Unable to determine the current dashboard state." onRetry={onRetry} />;
  }
}

export function DashboardContent() {
  const router = useRouter();
  const { data, isLoading, mutate } = useSWR("latest-revenue-snapshot", fetchLatestRevenueSnapshotState, {
    refreshInterval: (state) =>
      state?.status === "snapshot_missing" ? SNAPSHOT_MISSING_REFRESH_INTERVAL_MS : 0,
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const state: DashboardState = isLoading && !data ? { status: "loading" } : (data ?? { status: "loading" });

  useEffect(() => {
    if (state.status !== "unauthorized") {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      router.replace("/login");
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [router, state.status]);

  return (
    <SectionCard title="Revenue snapshot">
      {renderDashboardState(state, () => {
        void mutate();
      })}
    </SectionCard>
  );
}

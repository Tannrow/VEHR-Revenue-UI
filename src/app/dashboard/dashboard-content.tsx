"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";

import { SectionCard } from "@/components/page-shell";
import { RevenueWorkbench } from "@/components/revenue-os/workbench";
import { fetchClaimsIndex } from "@/lib/api/claims";
import { fetchLatestRevenueSnapshotState, type DashboardState } from "@/lib/api/revenue";
import {
  buildInsightMetrics,
  buildPipelineStages,
  buildPolicyRules,
  buildRevenueQueueItems,
} from "@/lib/revenue-os";

function formatRetryInterval(intervalMs: number): string {
  const seconds = Math.round(intervalMs / 1000);
  return `${seconds} second${seconds === 1 ? "" : "s"}`;
}

type DashboardStatusTone = "info" | "warning" | "error";

function getToneClasses(tone: DashboardStatusTone): string {
  switch (tone) {
    case "info":
      return "border-sky-500/40 bg-sky-500/10 text-sky-100";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-100";
    case "error":
      return "border-rose-500/40 bg-rose-500/10 text-rose-100";
  }
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={`dashboard-skeleton-${index}`}
            className="h-36 animate-pulse rounded-[22px] border border-white/8 bg-white/[0.04]"
          />
        ))}
      </div>
      <div className="h-24 animate-pulse rounded-[22px] border border-white/8 bg-white/[0.04]" />
      <div className="h-[420px] animate-pulse rounded-[24px] border border-white/8 bg-white/[0.03]" />
    </div>
  );
}

function StatusDetail({ detail }: { detail?: string }) {
  if (!detail) {
    return null;
  }

  return (
    <div className="rounded-md border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-200">
      <p className="font-medium uppercase tracking-wide text-zinc-400">Details</p>
      <p className="mt-2 whitespace-pre-wrap break-words">{detail}</p>
    </div>
  );
}

function DashboardStatusPanel({
  tone,
  title,
  message,
  detail,
  actions,
  guidance,
}: {
  tone: DashboardStatusTone;
  title: string;
  message: string;
  detail?: string;
  actions?: ReactNode;
  guidance?: ReactNode;
}) {
  return (
    <SectionCard title="Revenue snapshot" subtitle="The redesigned queue stays live once the backend snapshot is ready.">
      <div className="space-y-6 text-sm text-zinc-300">
        <div className={`space-y-3 rounded-md border px-4 py-3 ${getToneClasses(tone)}`}>
          <div>
            <p className="font-semibold text-white">{title}</p>
            <p className="mt-2 text-sm leading-6">{message}</p>
          </div>
          <StatusDetail detail={detail} />
          {guidance ? <div className="text-xs text-zinc-200">{guidance}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
      </div>
    </SectionCard>
  );
}

function DashboardStatusActions({
  onRetry,
  showSignIn,
}: {
  onRetry?: () => void;
  showSignIn?: boolean;
}) {
  return (
    <>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
        >
          Retry
        </button>
      ) : null}
      {showSignIn ? (
        <Link
          href="/login"
          className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black"
        >
          Go to sign in
        </Link>
      ) : null}
      <Link href="/diagnostics" className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white">
        Open diagnostics
      </Link>
    </>
  );
}

function renderDashboardState(
  state: DashboardState,
  autoRetryCount: number,
  onRetry: () => void,
): ReactNode {
  switch (state.status) {
    case "loading":
      return <DashboardSkeleton />;
    case "pending":
      return (
        <DashboardStatusPanel
          tone="info"
          title="Generating first snapshot"
          message={state.message}
          detail={state.detail}
          guidance={
            autoRetryCount < state.retryPolicy.maxAttempts
              ? `The UI will check again in ${formatRetryInterval(state.retryPolicy.intervalMs)}.`
              : "Automatic checks are paused for now. Retry after the backend finishes recovering."
          }
          actions={<DashboardStatusActions onRetry={onRetry} />}
        />
      );
    case "recoverable":
      return (
        <DashboardStatusPanel
          tone="warning"
          title="Snapshot temporarily unavailable"
          message={state.message}
          detail={state.detail}
          guidance={
            autoRetryCount < state.retryPolicy.maxAttempts
              ? `The UI will retry automatically in ${formatRetryInterval(state.retryPolicy.intervalMs)} while the backend catches up.`
              : "Automatic retries are paused to avoid hammering the backend. Retry when you're ready."
          }
          actions={<DashboardStatusActions onRetry={onRetry} />}
        />
      );
    case "unauthorized":
      return (
        <DashboardStatusPanel
          tone="warning"
          title="Session expired"
          message={state.message}
          detail={state.detail}
          guidance="Sign in again to refresh your session before returning to the dashboard."
          actions={<DashboardStatusActions showSignIn />}
        />
      );
    case "backend_failure":
      return (
        <DashboardStatusPanel
          tone="error"
          title="Revenue snapshot failed"
          message={state.message}
          detail={state.detail}
          guidance="Retry after the backend error is addressed, or open diagnostics to inspect the environment."
          actions={<DashboardStatusActions onRetry={onRetry} />}
        />
      );
    case "fatal":
      return (
        <DashboardStatusPanel
          tone="error"
          title="Unexpected dashboard response"
          message={state.message}
          detail={state.detail}
          guidance="The frontend received data it could not safely render. Retry once the response contract is corrected."
          actions={<DashboardStatusActions onRetry={onRetry} />}
        />
      );
    default:
      return (
        <DashboardStatusPanel
          tone="error"
          title="Unexpected dashboard response"
          message="Unable to determine the current dashboard state."
          actions={<DashboardStatusActions onRetry={onRetry} />}
        />
      );
  }
}

export function DashboardContent() {
  const [autoRetryState, setAutoRetryState] = useState<{ key: string; count: number }>({
    key: "idle",
    count: 0,
  });
  const { data, isLoading, mutate } = useSWR("latest-revenue-snapshot", fetchLatestRevenueSnapshotState, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const state = useMemo<DashboardState>(
    () => (isLoading && !data ? { status: "loading" } : (data ?? { status: "loading" })),
    [data, isLoading],
  );
  const autoRetryKey =
    state.status === "pending" || state.status === "recoverable"
      ? `${state.status}:${state.message}:${state.detail ?? ""}`
      : "idle";
  const autoRetryCount = autoRetryState.key === autoRetryKey ? autoRetryState.count : 0;
  const autoRetryIntervalMs =
    state.status === "pending" || state.status === "recoverable" ? state.retryPolicy.intervalMs : null;
  const autoRetryLimit = state.status === "pending" || state.status === "recoverable" ? state.retryPolicy.maxAttempts : 0;

  const { data: claimsState } = useSWR(state.status === "ready" ? "claims-index" : null, fetchClaimsIndex, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  useEffect(() => {
    if (state.status !== "pending" && state.status !== "recoverable") {
      return;
    }

    if (autoRetryIntervalMs === null || autoRetryCount >= autoRetryLimit) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setAutoRetryState((currentState) => ({
        key: autoRetryKey,
        count: currentState.key === autoRetryKey ? currentState.count + 1 : 1,
      }));
      void mutate();
    }, autoRetryIntervalMs);

    return () => window.clearTimeout(timeoutId);
  }, [autoRetryCount, autoRetryIntervalMs, autoRetryKey, autoRetryLimit, mutate, state.status]);

  const workbenchData = useMemo(() => {
    if (state.status !== "ready") {
      return null;
    }

    const claims = claimsState?.claims ?? [];
    const items = buildRevenueQueueItems(state.snapshot, claims);

    return {
      items,
      metrics: buildInsightMetrics(state.snapshot, items),
      pipelineStages: buildPipelineStages(items),
      policyRules: buildPolicyRules(items),
      snapshotGeneratedAt: state.snapshot.generated_at,
      claimsNotice: claimsState?.error ?? null,
    };
  }, [claimsState, state]);

  if (state.status !== "ready" || !workbenchData) {
    return renderDashboardState(state, autoRetryCount, () => {
      setAutoRetryState({
        key: autoRetryKey,
        count: 0,
      });
      void mutate();
    });
  }

  return <RevenueWorkbench {...workbenchData} />;
}

"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";

import { SectionCard } from "@/components/page-shell";
import { RevenueWorkbench } from "@/components/revenue-os/workbench";
import { fetchLatestRevenueSnapshotState, type DashboardState } from "@/lib/api/revenue";
import { fetchRevenueWorklist, runRevenueWorklistAction } from "@/lib/api/worklist";
import { buildInsightMetrics, buildRevenueQueueItems } from "@/lib/revenue-os";

const WORKLIST_SORT_VALUES = new Set(["created_at", "updated_at", "aging", "priority", "amount_at_risk"]);
const WORKLIST_DIRECTION_VALUES = new Set(["asc", "desc"]);
const DEFAULT_WORKLIST_PAGE_SIZE = 100;

function formatRetryInterval(intervalMs: number): string {
  const seconds = Math.round(intervalMs / 1000);
  return `${seconds} second${seconds === 1 ? "" : "s"}`;
}

function parsePositiveInteger(value: string | null, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return parsed;
}

function buildWorklistRequest(searchParamString: string): Record<string, string | number | null> {
  const params = new URLSearchParams(searchParamString);
  const sortBy = params.get("sort_by");
  const sortDirection = params.get("sort_direction");
  const status = params.get("status");
  const priority = params.get("priority");
  const type = params.get("type");
  const search = params.get("search");

  return {
    page: parsePositiveInteger(params.get("page"), 1),
    page_size: DEFAULT_WORKLIST_PAGE_SIZE,
    sort_by: sortBy && WORKLIST_SORT_VALUES.has(sortBy) ? sortBy : "priority",
    sort_direction: sortDirection && WORKLIST_DIRECTION_VALUES.has(sortDirection) ? sortDirection : "desc",
    status: status && status !== "All statuses" ? status : null,
    priority: priority && priority !== "All priorities" ? priority : null,
    type: type && type !== "All types" ? type : null,
    search: search?.trim() ? search.trim() : null,
  };
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

function getSnapshotNotice(state: DashboardState, autoRetryCount: number): string | null {
  switch (state.status) {
    case "loading":
      return "The AI command snapshot is still loading. Queue rows and summary cards below already come from the canonical backend worklist.";
    case "pending":
      return autoRetryCount < state.retryPolicy.maxAttempts
        ? `The AI command snapshot is still generating. Queue rows and summary cards stay live from the backend worklist while the snapshot retries every ${formatRetryInterval(
            state.retryPolicy.intervalMs,
          )}.`
        : "The AI command snapshot is still generating. Queue rows and summary cards remain live from the backend worklist while automatic snapshot retries stay paused.";
    case "recoverable":
      return "The AI command snapshot is temporarily unavailable. The queue and summary cards below are still the canonical backend worklist.";
    case "backend_failure":
      return "The AI command snapshot failed to load. The queue and summary cards below are still driven by the backend worklist contract.";
    case "fatal":
      return "The AI command snapshot returned an unexpected payload. The queue and summary cards below are still rendered from the backend worklist.";
    case "unauthorized":
      return "Refresh your session to recover the AI command snapshot. The queue and summary cards below remain sourced from the backend while your current access stays valid.";
    case "ready":
      return null;
    default:
      return null;
  }
}

function getWorklistErrorState(error: unknown): {
  title: string;
  message: string;
  detail?: string;
  showSignIn?: boolean;
} {
  const message = error instanceof Error ? error.message : "Unable to load the backend worklist.";
  const normalized = message.trim() || "Unable to load the backend worklist.";
  const lower = normalized.toLowerCase();

  if (
    lower.includes("session") ||
    lower.includes("sign in") ||
    lower.includes("unauthorized") ||
    lower.includes("forbidden") ||
    lower.includes("invalid token") ||
    lower.includes("invalid_token")
  ) {
    return {
      title: "Session expired",
      message: "Sign in again to restore access to the canonical backend worklist.",
      detail: normalized,
      showSignIn: true,
    };
  }

  return {
    title: "Canonical worklist unavailable",
    message: "The backend worklist could not be loaded, so the operator console cannot safely render workflow state.",
    detail: normalized,
  };
}

export function DashboardContent() {
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const worklistRequest = useMemo(() => buildWorklistRequest(searchParamString), [searchParamString]);
  const worklistKey = useMemo(() => `revenue-worklist:${JSON.stringify(worklistRequest)}`, [worklistRequest]);
  const [autoRetryState, setAutoRetryState] = useState<{ key: string; count: number }>({
    key: "idle",
    count: 0,
  });

  const {
    data: snapshotData,
    isLoading: snapshotIsLoading,
    mutate: mutateSnapshot,
  } = useSWR("latest-revenue-snapshot", fetchLatestRevenueSnapshotState, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const {
    data: worklistPage,
    error: worklistError,
    isLoading: worklistLoading,
    mutate: mutateWorklist,
  } = useSWR(worklistKey, () => fetchRevenueWorklist(worklistRequest), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const state = useMemo<DashboardState>(
    () => (snapshotIsLoading && !snapshotData ? { status: "loading" } : (snapshotData ?? { status: "loading" })),
    [snapshotData, snapshotIsLoading],
  );
  const autoRetryKey =
    state.status === "pending" || state.status === "recoverable"
      ? `${state.status}:${state.message}:${state.detail ?? ""}`
      : "idle";
  const autoRetryCount = autoRetryState.key === autoRetryKey ? autoRetryState.count : 0;
  const autoRetryIntervalMs =
    state.status === "pending" || state.status === "recoverable" ? state.retryPolicy.intervalMs : null;
  const autoRetryLimit = state.status === "pending" || state.status === "recoverable" ? state.retryPolicy.maxAttempts : 0;

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
      void mutateSnapshot();
    }, autoRetryIntervalMs);

    return () => window.clearTimeout(timeoutId);
  }, [autoRetryCount, autoRetryIntervalMs, autoRetryKey, autoRetryLimit, mutateSnapshot, state.status]);

  const workbenchData = useMemo(() => {
    if (!worklistPage) {
      return null;
    }

    return {
      items: buildRevenueQueueItems(worklistPage),
      metrics: buildInsightMetrics(worklistPage),
      typeOptions: Object.keys(worklistPage.summary.type_counts ?? {}).sort(),
      totalItems: worklistPage.total,
      currentPage: worklistPage.page,
      pageSize: worklistPage.page_size,
      totalPages: worklistPage.total_pages,
      sortBy: worklistPage.sort_by,
      sortDirection: worklistPage.sort_direction,
      snapshotNotice: getSnapshotNotice(state, autoRetryCount),
    };
  }, [autoRetryCount, state, worklistPage]);

  if (worklistLoading && !worklistPage) {
    return <DashboardSkeleton />;
  }

  if (!worklistPage) {
    if (!worklistError && state.status !== "loading") {
      return renderDashboardState(state, autoRetryCount, () => {
        setAutoRetryState({
          key: autoRetryKey,
          count: 0,
        });
        void mutateSnapshot();
      });
    }

    const worklistProblem = getWorklistErrorState(worklistError);
    return (
      <DashboardStatusPanel
        tone={worklistProblem.showSignIn ? "warning" : "error"}
        title={worklistProblem.title}
        message={worklistProblem.message}
        detail={worklistProblem.detail}
        guidance="The operator console only renders queue state from the backend worklist contract, so the queue is withheld until that contract is reachable again."
        actions={
          <DashboardStatusActions
            onRetry={() => {
              setAutoRetryState({
                key: autoRetryKey,
                count: 0,
              });
              void mutateWorklist();
              void mutateSnapshot();
            }}
            showSignIn={worklistProblem.showSignIn}
          />
        }
      />
    );
  }

  if (!workbenchData) {
    return <DashboardSkeleton />;
  }

  async function handleMarkInProgress(itemIds: string[]) {
    const response = await runRevenueWorklistAction({
      workItemIds: itemIds,
      action: "mark_in_progress",
    });
    await Promise.all([mutateWorklist(), mutateSnapshot()]);
    return response;
  }

  return <RevenueWorkbench {...workbenchData} onMarkInProgress={handleMarkInProgress} />;
}

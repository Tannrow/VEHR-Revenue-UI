"use client";

import { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  type InsightMetric,
  type PipelineStage,
  type PolicyRule,
  type QueueItem,
  type QueuePriority,
  type QueueStatus,
} from "@/lib/revenue-os";

const ALL_QUEUES = "All queues";
const ALL_PRIORITIES = "All priorities";
const ALL_STATUSES = "All statuses";
const SAVED_VIEWS = ["Critical priority", "Denied claims", "Open balances", "Resolved claims"] as const;

type PanelName = "insights" | "policy" | "pipeline" | null;

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

function formatTimestampLabel(value: string): string {
  const parsed = new Date(value);

  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }

  return parsed.toLocaleString();
}

function getPriorityClasses(priority: QueuePriority): string {
  switch (priority) {
    case "critical":
      return "border-rose-400/30 bg-rose-400/10 text-rose-200";
    case "high":
      return "border-amber-400/30 bg-amber-400/10 text-amber-200";
    case "medium":
      return "border-sky-400/30 bg-sky-400/10 text-sky-200";
    case "low":
      return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }
}

function getStatusClasses(status: QueueStatus): string {
  switch (status) {
    case "blocked":
      return "bg-rose-400/10 text-rose-200";
    case "appeal":
      return "bg-violet-400/10 text-violet-200";
    case "ready":
      return "bg-emerald-400/10 text-emerald-200";
    case "resolved":
      return "bg-slate-400/10 text-slate-200";
    case "new":
    default:
      return "bg-amber-400/10 text-amber-200";
  }
}

function getMetricAction(metricLabel: string): {
  queue?: string;
  priority?: string;
  status?: string;
  search?: string;
  panel: PanelName;
} {
  switch (metricLabel) {
    case "Total exposure":
      return { panel: "insights" };
    case "30-day recovery":
      return { queue: "Open balances", panel: "insights" };
    case "High-risk claims":
      return { status: "blocked", panel: "insights" };
    case "Critical pre-submission":
      return { priority: "critical", panel: "insights" };
    default:
      return { panel: "insights" };
  }
}

function getSavedViewState(view: string): {
  queue?: string;
  priority?: string;
  status?: string;
  search?: string;
} {
  switch (view) {
    case "Critical priority":
      return { priority: "critical" };
    case "Denied claims":
      return { queue: "Denied claims", status: "blocked" };
    case "Open balances":
      return { queue: "Open balances" };
    case "Resolved claims":
      return { status: "resolved" };
    default:
      return {};
  }
}

function getActiveViewLabel(state: {
  queueFilter: string;
  priorityFilter: string;
  statusFilter: string;
  searchText: string;
}) {
  return (
    SAVED_VIEWS.find((view) => {
      const saved = getSavedViewState(view);

      return (
        (saved.queue ?? ALL_QUEUES) === state.queueFilter &&
        (saved.priority ?? ALL_PRIORITIES) === state.priorityFilter &&
        (saved.status ?? ALL_STATUSES) === state.statusFilter &&
        (saved.search ?? "") === state.searchText
      );
    }) ?? null
  );
}

function InsightStrip({
  active,
  metrics,
  onMetricAction,
}: {
  active: boolean;
  metrics: InsightMetric[];
  onMetricAction: (metricLabel: string) => void;
}) {
  return (
    <div
      className={`grid gap-4 xl:grid-cols-4 ${
        active ? "rounded-[28px] border border-sky-400/20 bg-sky-400/[0.03] p-3" : ""
      }`}
    >
      {metrics.map((metric) => (
        <button
          key={metric.label}
          type="button"
          onClick={() => onMetricAction(metric.label)}
          className="rounded-[22px] border border-white/8 bg-white/[0.035] p-4 text-left backdrop-blur-sm hover:-translate-y-[1px] hover:border-white/14 hover:bg-white/[0.05]"
        >
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{metric.label}</p>
          <div className="mt-4 flex items-end justify-between gap-3">
            <div>
              <p className="text-[2rem] font-semibold tracking-[-0.04em] text-white">{metric.value}</p>
              <p className="mt-2 text-sm text-slate-300">{metric.trend}</p>
            </div>
            <span className="rounded-full border border-white/8 bg-white/[0.05] px-3 py-1 text-xs font-medium text-slate-300">
              {metric.change}
            </span>
          </div>
          <p className="mt-4 text-sm text-sky-200/90">{metric.drillLabel} →</p>
        </button>
      ))}
    </div>
  );
}

function FilterBar(props: {
  queueFilter: string;
  priorityFilter: string;
  statusFilter: string;
  searchText: string;
  queueOptions: string[];
  activeView: string | null;
  onQueueChange: (value: string) => void;
  onPriorityChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onApplySavedView: (view: string) => void;
}) {
  const {
    queueFilter,
    priorityFilter,
    statusFilter,
    searchText,
    queueOptions,
    activeView,
    onQueueChange,
    onPriorityChange,
    onStatusChange,
    onSearchChange,
    onApplySavedView,
  } = props;

  return (
    <div className="space-y-3 rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {SAVED_VIEWS.map((view) => {
            const active = activeView === view;
            return (
              <button
                key={view}
                type="button"
                onClick={() => onApplySavedView(view)}
                className={`rounded-full border px-3 py-2 text-sm transition ${
                  active
                    ? "border-white/14 bg-white/[0.12] text-white"
                    : "border-white/8 bg-white/[0.04] text-slate-300 hover:border-white/14 hover:bg-white/[0.08]"
                }`}
              >
                {view}
              </button>
            );
          })}
        </div>
        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Filters persist across navigation</p>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(180px,0.7fr))]">
        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Search</span>
          <input
            value={searchText}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Claim, payer, patient, status, or next action"
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
          />
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Queue</span>
          <select
            value={queueFilter}
            onChange={(event) => onQueueChange(event.target.value)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            <option value={ALL_QUEUES}>All queues</option>
            {queueOptions.map((queue) => (
              <option key={queue} value={queue}>
                {queue}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Priority</span>
          <select
            value={priorityFilter}
            onChange={(event) => onPriorityChange(event.target.value)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            <option value={ALL_PRIORITIES}>All priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Status</span>
          <select
            value={statusFilter}
            onChange={(event) => onStatusChange(event.target.value)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            <option value={ALL_STATUSES}>All statuses</option>
            <option value="new">New</option>
            <option value="blocked">Blocked</option>
            <option value="ready">Ready</option>
            <option value="appeal">Appeal</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
      </div>
    </div>
  );
}

function BulkActionBar(props: {
  selectedCount: number;
  hiddenSelectedCount: number;
  onRunAction: (label: string) => void;
  onClearSelection: () => void;
}) {
  const { selectedCount, hiddenSelectedCount, onRunAction, onClearSelection } = props;

  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3 rounded-[22px] border border-sky-400/20 bg-sky-400/[0.05] px-4 py-4 backdrop-blur-sm xl:flex-row xl:items-center xl:justify-between">
      <div className="space-y-1">
        <p className="text-sm font-semibold text-white">{selectedCount} claims selected for bulk action</p>
        <p className="text-sm text-slate-300">
          Apply one action across the filtered cohort without leaving the queue.
          {hiddenSelectedCount > 0 ? ` ${hiddenSelectedCount} selected item(s) are hidden by the current filters.` : ""}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {["Open claim records", "Route for review", "Recheck tomorrow"].map((label) => (
          <button
            key={label}
            type="button"
            onClick={() => onRunAction(label)}
            className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-2 text-sm text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.09]"
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={onClearSelection}
          className="rounded-full border border-white/8 px-3 py-2 text-sm text-slate-300 hover:border-white/18 hover:text-white"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

function WorkQueueTable(props: {
  items: QueueItem[];
  selectedId: string | null;
  selectedIds: string[];
  onSelect: (item: QueueItem) => void;
  onToggleSelect: (itemId: string) => void;
  onToggleSelectVisible: () => void;
}) {
  const { items, selectedId, selectedIds, onSelect, onToggleSelect, onToggleSelectVisible } = props;
  const visibleIds = items.map((item) => item.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

  return (
    <div className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(18,22,30,0.96),rgba(14,17,24,0.98))] backdrop-blur-sm">
      <div className="flex flex-col gap-4 border-b border-white/8 px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Primary work queue</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Live backend claims requiring operator action</h3>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={onToggleSelectVisible}
            className="rounded-full border border-white/10 px-3 py-2 text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
          >
            {allVisibleSelected ? "Clear visible" : "Select visible"}
          </button>
          <button
            type="button"
            className="rounded-full border border-white/10 px-3 py-2 text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
          >
            Review balances
          </button>
          <button
            type="button"
            className="rounded-full border border-white/10 px-3 py-2 text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
          >
            Export queue
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/[0.025] text-[11px] uppercase tracking-[0.24em] text-slate-500">
            <tr>
              <th className="px-4 py-3">
                <button
                  type="button"
                  onClick={onToggleSelectVisible}
                  className="flex h-5 w-5 items-center justify-center rounded border border-white/10 bg-white/[0.03] text-[10px] text-slate-300"
                  aria-label={allVisibleSelected ? "Clear visible selection" : "Select visible rows"}
                >
                  {allVisibleSelected ? "✓" : ""}
                </button>
              </th>
              <th className="px-5 py-3">Work</th>
              <th className="px-4 py-3">Queue</th>
              <th className="px-4 py-3">Live status</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Value / hr</th>
              <th className="px-4 py-3">Aging</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/6">
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-5 py-10 text-center text-sm text-slate-400">
                  No live queue items match the current filters.
                </td>
              </tr>
            ) : null}

            {items.map((item) => {
              const rowSelected = item.id === selectedId;
              const checked = selectedIds.includes(item.id);
              const identity = [item.patient, item.payer].filter(Boolean).join(" · ");

              return (
                <tr
                  key={item.id}
                  className={`cursor-pointer ${rowSelected ? "bg-white/[0.055]" : "hover:bg-white/[0.03]"}`}
                  onClick={() => onSelect(item)}
                >
                  <td className="px-4 py-4 align-top" onClick={(event) => event.stopPropagation()}>
                    <button
                      type="button"
                      onClick={() => onToggleSelect(item.id)}
                      className={`flex h-5 w-5 items-center justify-center rounded border text-[10px] ${
                        checked
                          ? "border-sky-300/30 bg-sky-300/15 text-sky-100"
                          : "border-white/10 bg-white/[0.03] text-transparent"
                      }`}
                      aria-label={`Select ${item.claimId}`}
                    >
                      ✓
                    </button>
                  </td>
                  <td className="px-5 py-4 align-top">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-white">{item.claimId}</span>
                        <span className={`rounded-full px-2 py-1 text-xs ${getStatusClasses(item.status)}`}>{item.status}</span>
                        {item.claimId !== item.sourceClaimId ? (
                          <span className="rounded-full bg-white/6 px-2 py-1 text-xs text-slate-400">{item.sourceClaimId}</span>
                        ) : null}
                      </div>
                      <div>
                        <p className="text-slate-200">{item.nextAction}</p>
                        <p className="mt-1 text-xs text-slate-500">{identity || item.payer}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.queue}</td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.claimStatus}</td>
                  <td className="px-4 py-4 align-top">
                    <span
                      className={`rounded-full border px-2 py-1 text-xs font-medium uppercase tracking-[0.18em] ${getPriorityClasses(item.priority)}`}
                    >
                      {item.priority}
                    </span>
                  </td>
                  <td className="px-4 py-4 align-top text-white">{formatMoney(item.valuePerHourCents)}</td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.agingDays}d</td>
                  <td className="px-4 py-4 align-top">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelect(item);
                      }}
                      className="rounded-full border border-white/8 bg-white/[0.035] px-3 py-2 text-xs font-medium text-slate-200 hover:border-white/14 hover:bg-white/[0.08]"
                    >
                      Open drawer
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ClaimDrawer({ item }: { item: QueueItem | null }) {
  if (!item) {
    return (
      <div className="rounded-[24px] border border-dashed border-white/8 bg-white/[0.02] p-5 text-sm text-slate-400">
        No queue items match the current filters.
      </div>
    );
  }

  return (
    <div className="space-y-5 rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.96),rgba(15,18,25,0.98))] p-5 backdrop-blur-sm">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Claim drawer</p>
            <h3 className="mt-1 text-xl font-semibold text-white">{item.claimId}</h3>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] ${getPriorityClasses(item.priority)}`}>
            {item.priority}
          </span>
        </div>
        <p className="text-sm leading-6 text-slate-300">{item.summary}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {[
          ["Displayed claim ID", item.claimId],
          ["Source claim ID", item.sourceClaimId],
          ["Patient", item.patient ?? "Unavailable"],
          ["Payer", item.payer],
          ["Live status", item.claimStatus],
          ["Queue", item.queue],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-white/8 bg-black/20 p-3">
            <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{label}</p>
            <p className="mt-2 break-words text-sm text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Next operator move</p>
            <p className="mt-2 text-base font-medium text-white">{item.nextAction}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm font-medium text-white hover:border-white/18 hover:bg-white/[0.09]"
            >
              Take action
            </button>
            <button
              type="button"
              className="rounded-full border border-white/8 px-4 py-2 text-sm text-slate-300 hover:border-white/18 hover:text-white"
            >
              Open claim API
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-white">Timeline</h4>
          <span className="text-sm text-slate-500">Live backend activity</span>
        </div>
        <div className="space-y-3">
          {item.timeline.map((entry) => (
            <div key={`${entry.at}-${entry.event}`} className="rounded-2xl border border-white/8 bg-black/20 p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-white">{entry.event}</p>
                <span className="text-xs text-slate-500">{entry.at}</span>
              </div>
              <p className="mt-1 text-sm text-slate-400">{entry.actor}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DecisionSupportPanel({ item }: { item: QueueItem | null }) {
  if (!item) {
    return (
      <div className="rounded-[24px] border border-dashed border-white/8 bg-white/[0.02] p-5 text-sm text-slate-400">
        Decision support appears when a live claim is selected.
      </div>
    );
  }

  return (
    <div className="space-y-5 rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(22,26,34,0.96),rgba(16,19,26,0.98))] p-5 backdrop-blur-sm">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Decision support</p>
            <h3 className="mt-1 text-xl font-semibold text-white">Recommended next step</h3>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-slate-200">
            {item.agingDays}d aging
          </span>
        </div>
        <p className="text-sm leading-6 text-slate-300">{item.summary}</p>
      </div>

      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-white">Why it is on the queue</h4>
        {item.evidence.map((entry) => (
          <div key={entry.label} className="rounded-2xl border border-white/8 bg-black/20 p-3">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">{entry.label}</p>
            <p className="mt-2 text-sm text-slate-200">{entry.detail}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-white">Suggested actions</h4>
          <span className="rounded-full border border-white/8 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">
            Live queue
          </span>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
          {item.nextAction}
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
          Review payer status before closing the claim.
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
          Confirm the claim record stays aligned with the latest snapshot.
        </div>
      </div>
    </div>
  );
}

function QueueHealthPanel({
  active,
  stages,
  onOpen,
}: {
  active: boolean;
  stages: PipelineStage[];
  onOpen: () => void;
}) {
  return (
    <div
      className={`rounded-[24px] border bg-[linear-gradient(180deg,rgba(20,24,33,0.96),rgba(15,18,25,0.98))] p-5 backdrop-blur-sm ${
        active ? "border-sky-400/20 shadow-[0_0_0_1px_rgba(125,211,252,0.1)]" : "border-white/8"
      }`}
    >
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Queue health</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Live workflow stages from the current snapshot</h3>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="rounded-full border border-white/10 px-3 py-2 text-sm text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
        >
          Focus queue health
        </button>
      </div>
      <div className="grid gap-3 xl:grid-cols-5">
        {stages.map((stage) => (
          <div key={stage.label} className="relative rounded-2xl border border-white/8 bg-black/20 p-4">
            <div
              className={`absolute inset-x-4 top-0 h-1 rounded-b-full ${
                stage.tone === "good"
                  ? "bg-emerald-400/60"
                  : stage.tone === "warning"
                    ? "bg-amber-400/60"
                    : "bg-sky-400/60"
              }`}
            />
            <p className="mt-2 text-[11px] uppercase tracking-[0.24em] text-slate-500">{stage.label}</p>
            <p className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white">{stage.count}</p>
            <p className="mt-3 text-sm text-slate-300">{stage.action}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function PolicyPanel({
  active,
  rules,
  onOpen,
}: {
  active: boolean;
  rules: PolicyRule[];
  onOpen: () => void;
}) {
  return (
    <div
      className={`rounded-[24px] border bg-[linear-gradient(180deg,rgba(20,24,33,0.96),rgba(15,18,25,0.98))] p-5 backdrop-blur-sm ${
        active ? "border-sky-400/20 shadow-[0_0_0_1px_rgba(125,211,252,0.1)]" : "border-white/8"
      }`}
    >
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Policy engine</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Routing rules grounded in live queue conditions</h3>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="rounded-full border border-white/10 px-3 py-2 text-sm text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
        >
          Focus policy
        </button>
      </div>
      <div className="space-y-3">
        {rules.map((rule) => (
          <div key={rule.id} className="rounded-2xl border border-white/8 bg-black/20 p-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-white/6 px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-500">{rule.id}</span>
                  <h4 className="text-base font-semibold text-white">{rule.name}</h4>
                </div>
                <p className="text-sm text-slate-300">
                  <span className="text-slate-500">If</span> {rule.condition}
                </p>
                <p className="text-sm text-slate-300">
                  <span className="text-slate-500">Then</span> {rule.outcome}
                </p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-slate-300">
                {rule.coverage}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RevenueWorkbench({
  items,
  metrics,
  pipelineStages,
  policyRules,
  snapshotGeneratedAt,
  claimsNotice,
}: {
  items: QueueItem[];
  metrics: InsightMetric[];
  pipelineStages: PipelineStage[];
  policyRules: PolicyRule[];
  snapshotGeneratedAt: string;
  claimsNotice?: string | null;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkNotice, setBulkNotice] = useState<string | null>(null);

  const queueFilter = searchParams.get("queue") ?? ALL_QUEUES;
  const priorityFilter = searchParams.get("priority") ?? ALL_PRIORITIES;
  const statusFilter = searchParams.get("status") ?? ALL_STATUSES;
  const searchText = searchParams.get("search") ?? "";
  const selectedId = searchParams.get("selected");
  const panel = (searchParams.get("panel") as PanelName) ?? null;

  const queueOptions = useMemo(() => Array.from(new Set(items.map((item) => item.queue))).sort(), [items]);

  const activeView = useMemo(
    () => getActiveViewLabel({ queueFilter, priorityFilter, statusFilter, searchText }),
    [priorityFilter, queueFilter, searchText, statusFilter],
  );

  const filteredItems = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();

    return items.filter((item) => {
      const queueMatch = queueFilter === ALL_QUEUES || item.queue === queueFilter;
      const priorityMatch = priorityFilter === ALL_PRIORITIES || item.priority === (priorityFilter as QueuePriority);
      const statusMatch = statusFilter === ALL_STATUSES || item.status === (statusFilter as QueueStatus);
      const searchMatch =
        normalizedSearch.length === 0 ||
        [
          item.claimId,
          item.sourceClaimId,
          item.patient ?? "",
          item.payer,
          item.queue,
          item.claimStatus,
          item.nextAction,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch);

      return queueMatch && priorityMatch && statusMatch && searchMatch;
    });
  }, [items, priorityFilter, queueFilter, searchText, statusFilter]);

  const updateQuery = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("owner");

      Object.entries(updates).forEach(([key, value]) => {
        const shouldDelete =
          value === null ||
          value === "" ||
          value === ALL_QUEUES ||
          value === ALL_PRIORITIES ||
          value === ALL_STATUSES;

        if (shouldDelete) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      });

      const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;

      startTransition(() => {
        router.replace(nextUrl, { scroll: false });
      });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    const nextSelectedId = filteredItems[0]?.id ?? null;

    if (filteredItems.length === 0) {
      if (selectedId) {
        updateQuery({ selected: null });
      }
      return;
    }

    if (!selectedId || !filteredItems.some((item) => item.id === selectedId)) {
      updateQuery({ selected: nextSelectedId });
    }
  }, [filteredItems, selectedId, updateQuery]);

  useEffect(() => {
    if (!bulkNotice) {
      return;
    }

    const timeout = window.setTimeout(() => setBulkNotice(null), 4000);

    return () => window.clearTimeout(timeout);
  }, [bulkNotice]);

  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;
  const hiddenSelectedCount = selectedIds.filter((id) => !filteredItems.some((item) => item.id === id)).length;

  function toggleSelect(itemId: string) {
    setSelectedIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleSelectVisible() {
    const visibleIds = filteredItems.map((item) => item.id);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

    setSelectedIds((current) =>
      allVisibleSelected
        ? current.filter((id) => !visibleIds.includes(id))
        : Array.from(new Set([...current, ...visibleIds])),
    );
  }

  function applySavedView(view: string) {
    const nextState = getSavedViewState(view);
    updateQuery({
      queue: nextState.queue ?? null,
      priority: nextState.priority ?? null,
      status: nextState.status ?? null,
      search: nextState.search ?? null,
      panel: "insights",
    });
  }

  function handleMetricAction(metricLabel: string) {
    const action = getMetricAction(metricLabel);
    updateQuery({
      queue: action.queue ?? null,
      priority: action.priority ?? null,
      status: action.status ?? null,
      search: action.search ?? null,
      panel: action.panel,
    });
  }

  function handleBulkAction(actionLabel: string) {
    setBulkNotice(`${actionLabel} prepared for ${selectedIds.length} selected claim${selectedIds.length === 1 ? "" : "s"}.`);
  }

  return (
    <div className="space-y-6">
      <div className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm">
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Live snapshot</p>
        <div className="mt-3 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <p className="text-sm text-slate-200">Latest revenue snapshot generated {formatTimestampLabel(snapshotGeneratedAt)}.</p>
          <p className="text-sm text-slate-400">{items.length} live queue item{items.length === 1 ? "" : "s"} loaded.</p>
        </div>
        {claimsNotice ? (
          <p className="mt-3 rounded-2xl border border-amber-500/20 bg-amber-500/[0.08] px-4 py-3 text-sm text-amber-100">
            Claim labels could not be loaded from the claims API, so the queue is using snapshot-only context. {claimsNotice}
          </p>
        ) : null}
      </div>

      <InsightStrip active={panel === "insights"} metrics={metrics} onMetricAction={handleMetricAction} />

      <FilterBar
        queueFilter={queueFilter}
        priorityFilter={priorityFilter}
        statusFilter={statusFilter}
        searchText={searchText}
        queueOptions={queueOptions}
        activeView={activeView}
        onQueueChange={(value) => updateQuery({ queue: value })}
        onPriorityChange={(value) => updateQuery({ priority: value })}
        onStatusChange={(value) => updateQuery({ status: value })}
        onSearchChange={(value) => updateQuery({ search: value })}
        onApplySavedView={applySavedView}
      />

      <BulkActionBar
        selectedCount={selectedIds.length}
        hiddenSelectedCount={hiddenSelectedCount}
        onRunAction={handleBulkAction}
        onClearSelection={() => setSelectedIds([])}
      />

      {bulkNotice ? (
        <div className="rounded-[20px] border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-3 text-sm text-emerald-100">
          {bulkNotice}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)_minmax(320px,0.9fr)]">
        <WorkQueueTable
          items={filteredItems}
          selectedId={selectedItem?.id ?? null}
          selectedIds={selectedIds}
          onSelect={(item) => updateQuery({ selected: item.id })}
          onToggleSelect={toggleSelect}
          onToggleSelectVisible={toggleSelectVisible}
        />
        <ClaimDrawer item={selectedItem} />
        <DecisionSupportPanel item={selectedItem} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <QueueHealthPanel active={panel === "pipeline"} stages={pipelineStages} onOpen={() => updateQuery({ panel: "pipeline" })} />
        <PolicyPanel active={panel === "policy"} rules={policyRules} onOpen={() => updateQuery({ panel: "policy" })} />
      </div>
    </div>
  );
}

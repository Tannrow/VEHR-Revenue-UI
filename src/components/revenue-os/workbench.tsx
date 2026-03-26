"use client";

import { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { RevenueWorklistActionResponse } from "@/lib/api/worklist";
import {
  type InsightMetric,
  type QueueItem,
  type QueuePriority,
  type QueueStatus,
} from "@/lib/revenue-os";

const ALL_TYPES = "All types";
const ALL_PRIORITIES = "All priorities";
const ALL_STATUSES = "All statuses";
const DEFAULT_SORT_BY = "priority";
const DEFAULT_SORT_DIRECTION = "desc";
const SAVED_VIEWS = ["Critical priority", "Needs review", "Denials", "Unassigned"] as const;
const SORT_OPTIONS = [
  { value: "priority", label: "Priority" },
  { value: "updated_at", label: "Updated" },
  { value: "created_at", label: "Created" },
  { value: "aging", label: "Aging" },
  { value: "amount_at_risk", label: "Amount at risk" },
] as const;

type SortValue = (typeof SORT_OPTIONS)[number]["value"];
type SortDirection = "asc" | "desc";

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

function formatTimestampLabel(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
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
    default:
      return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }
}

function getStatusClasses(status: QueueStatus): string {
  switch (status) {
    case "needs_review":
      return "bg-rose-400/10 text-rose-200";
    case "in_progress":
      return "bg-sky-400/10 text-sky-200";
    case "resolved":
      return "bg-slate-400/10 text-slate-200";
    case "open":
    default:
      return "bg-amber-400/10 text-amber-200";
  }
}

function getSavedViewState(view: string): {
  type?: string;
  priority?: string;
  status?: string;
  search?: string;
} {
  switch (view) {
    case "Critical priority":
      return { priority: "critical" };
    case "Needs review":
      return { status: "needs_review" };
    case "Denials":
      return { type: "DENIAL" };
    case "Unassigned":
      return { search: "unassigned" };
    default:
      return {};
  }
}

function getActiveViewLabel(state: {
  typeFilter: string;
  priorityFilter: string;
  statusFilter: string;
  searchText: string;
}) {
  return (
    SAVED_VIEWS.find((view) => {
      const saved = getSavedViewState(view);
      return (
        (saved.type ?? ALL_TYPES) === state.typeFilter &&
        (saved.priority ?? ALL_PRIORITIES) === state.priorityFilter &&
        (saved.status ?? ALL_STATUSES) === state.statusFilter &&
        (saved.search ?? "") === state.searchText
      );
    }) ?? null
  );
}

function normalizeSortValue(value: string | null | undefined, fallback: SortValue): SortValue {
  return SORT_OPTIONS.some((option) => option.value === value) ? (value as SortValue) : fallback;
}

function normalizeSortDirection(value: string | null | undefined, fallback: SortDirection): SortDirection {
  return value === "asc" || value === "desc" ? value : fallback;
}

function InsightStrip({
  metrics,
}: {
  metrics: InsightMetric[];
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-4">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="rounded-[22px] border border-white/8 bg-white/[0.035] p-4 text-left backdrop-blur-sm"
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
          <p className="mt-4 text-sm text-sky-200/90">{metric.drillLabel}</p>
        </div>
      ))}
    </div>
  );
}

function FilterBar(props: {
  typeFilter: string;
  priorityFilter: string;
  statusFilter: string;
  searchText: string;
  sortBy: SortValue;
  sortDirection: SortDirection;
  typeOptions: string[];
  activeView: string | null;
  onTypeChange: (value: string) => void;
  onPriorityChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onSortByChange: (value: SortValue) => void;
  onSortDirectionChange: (value: SortDirection) => void;
  onApplySavedView: (view: string) => void;
}) {
  const {
    typeFilter,
    priorityFilter,
    statusFilter,
    searchText,
    sortBy,
    sortDirection,
    typeOptions,
    activeView,
    onTypeChange,
    onPriorityChange,
    onStatusChange,
    onSearchChange,
    onSortByChange,
    onSortDirectionChange,
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
        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Server-generated workflow state</p>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_repeat(5,minmax(150px,0.7fr))]">
        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Search</span>
          <input
            value={searchText}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Claim, payer, patient, type, reason, or assignee"
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
          />
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Type</span>
          <select
            value={typeFilter}
            onChange={(event) => onTypeChange(event.target.value)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            <option value={ALL_TYPES}>All types</option>
            {typeOptions.map((type) => (
              <option key={type} value={type}>
                {type}
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
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="needs_review">Needs review</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Sort</span>
          <select
            value={sortBy}
            onChange={(event) => onSortByChange(event.target.value as SortValue)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="rounded-[18px] border border-white/8 bg-[#12161f] px-4 py-3">
          <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Direction</span>
          <select
            value={sortDirection}
            onChange={(event) => onSortDirectionChange(event.target.value as SortDirection)}
            className="mt-2 w-full bg-transparent text-sm text-slate-200 outline-none"
          >
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </label>
      </div>

      <p className="text-sm text-slate-400">
        Search, type, status, priority, sorting, and pagination all query the backend worklist API.
      </p>
    </div>
  );
}

function BulkActionBar(props: {
  selectedCount: number;
  hiddenSelectedCount: number;
  isSubmitting: boolean;
  onMarkInProgress: () => void;
  onClearSelection: () => void;
}) {
  const { selectedCount, hiddenSelectedCount, isSubmitting, onMarkInProgress, onClearSelection } = props;

  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3 rounded-[22px] border border-sky-400/20 bg-sky-400/[0.05] px-4 py-4 backdrop-blur-sm xl:flex-row xl:items-center xl:justify-between">
      <div className="space-y-1">
        <p className="text-sm font-semibold text-white">{selectedCount} work item{selectedCount === 1 ? "" : "s"} selected</p>
        <p className="text-sm text-slate-300">
          Bulk actions are limited to backend-supported workflow actions.
          {hiddenSelectedCount > 0 ? ` ${hiddenSelectedCount} selected item(s) are hidden by the current filters.` : ""}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onMarkInProgress}
          disabled={isSubmitting}
          className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-60 hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.09]"
        >
          {isSubmitting ? "Updating..." : "Mark in progress"}
        </button>
        <button
          type="button"
          onClick={onClearSelection}
          disabled={isSubmitting}
          className="rounded-full border border-white/8 px-3 py-2 text-sm text-slate-300 disabled:cursor-not-allowed disabled:opacity-60 hover:border-white/18 hover:text-white"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

function PaginationBar({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  visibleCount,
  onPageChange,
}: {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  visibleCount: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-4 backdrop-blur-sm xl:flex-row xl:items-center xl:justify-between">
      <div className="space-y-1 text-sm text-slate-300">
        <p className="font-medium text-white">
          Server page {currentPage} of {Math.max(totalPages, 1)}
        </p>
        <p>
          {totalItems} canonical work item{totalItems === 1 ? "" : "s"} on the backend. Showing {visibleCount} row
          {visibleCount === 1 ? "" : "s"} from a {pageSize}-item page.
        </p>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="rounded-full border border-white/8 px-3 py-2 text-sm text-slate-300 disabled:cursor-not-allowed disabled:opacity-50 hover:border-white/18 hover:text-white"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="rounded-full border border-white/8 px-3 py-2 text-sm text-slate-300 disabled:cursor-not-allowed disabled:opacity-50 hover:border-white/18 hover:text-white"
        >
          Next
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
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Canonical work queue</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Backend-owned revenue workflow items</h3>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={onToggleSelectVisible}
            className="rounded-full border border-white/10 px-3 py-2 text-slate-300 hover:-translate-y-[1px] hover:border-white/20 hover:text-white"
          >
            {allVisibleSelected ? "Clear visible" : "Select visible"}
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
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">SLA</th>
              <th className="px-4 py-3">Amount at risk</th>
              <th className="px-4 py-3">Aging</th>
              <th className="px-4 py-3">Assignee</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/6">
            {items.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-5 py-10 text-center text-sm text-slate-400">
                  No backend work items match the current filters.
                </td>
              </tr>
            ) : null}

            {items.map((item) => {
              const rowSelected = item.id === selectedId;
              const checked = selectedIds.includes(item.id);
              const identity = item.subtitle || [item.patient, item.payer].filter(Boolean).join(" · ");
              const assigneeLabel = item.assignee.userName ?? item.assignee.teamLabel ?? "Unassigned";

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
                      aria-label={`Select ${item.title}`}
                    >
                      ✓
                    </button>
                  </td>
                  <td className="px-5 py-4 align-top">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-white">{item.title}</span>
                        <span className={`rounded-full px-2 py-1 text-xs ${getStatusClasses(item.status)}`}>{item.status}</span>
                      </div>
                      <div>
                        <p className="text-slate-200">{item.reason}</p>
                        <p className="mt-1 text-xs text-slate-500">{identity || item.payer}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.type}</td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.status}</td>
                  <td className="px-4 py-4 align-top">
                    <span
                      className={`rounded-full border px-2 py-1 text-xs font-medium uppercase tracking-[0.18em] ${getPriorityClasses(item.priority)}`}
                    >
                      {item.priority}
                    </span>
                  </td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.slaState}</td>
                  <td className="px-4 py-4 align-top text-white">{formatMoney(item.amountAtRiskCents)}</td>
                  <td className="px-4 py-4 align-top text-slate-300">{item.agingDays}d</td>
                  <td className="px-4 py-4 align-top text-slate-300">{assigneeLabel}</td>
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
        No work items match the current filters.
      </div>
    );
  }

  return (
    <div className="space-y-5 rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(20,24,33,0.96),rgba(15,18,25,0.98))] p-5 backdrop-blur-sm">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Work item</p>
            <h3 className="mt-1 text-xl font-semibold text-white">{item.title}</h3>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] ${getPriorityClasses(item.priority)}`}>
            {item.priority}
          </span>
        </div>
        <p className="text-sm leading-6 text-slate-300">{item.reason}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {[
          ["Type", item.type],
          ["Status", item.status],
          ["SLA", item.slaState],
          ["Escalation", item.escalationState],
          ["Patient", item.patient ?? "Unavailable"],
          ["Payer", item.payer],
          ["Facility", item.facility ?? "Unavailable"],
          ["Assignee", item.assignee.userName ?? item.assignee.teamLabel ?? "Unassigned"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-white/8 bg-black/20 p-3">
            <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{label}</p>
            <p className="mt-2 break-words text-sm text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
        <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Reason codes</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {item.reasonCodes.map((code) => (
            <span key={code} className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs text-slate-200">
              {code}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function DecisionSupportPanel({
  item,
  isSubmitting,
  onMarkInProgress,
}: {
  item: QueueItem | null;
  isSubmitting: boolean;
  onMarkInProgress: (itemIds: string[]) => Promise<RevenueWorklistActionResponse>;
}) {
  if (!item) {
    return (
      <div className="rounded-[24px] border border-dashed border-white/8 bg-white/[0.02] p-5 text-sm text-slate-400">
        Decision support appears when a backend work item is selected.
      </div>
    );
  }

  const canMarkInProgress = item.allowedActions.includes("mark_in_progress");

  return (
    <div className="space-y-5 rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,rgba(22,26,34,0.96),rgba(16,19,26,0.98))] p-5 backdrop-blur-sm">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Decision support</p>
            <h3 className="mt-1 text-xl font-semibold text-white">Backend recommended next step</h3>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-slate-200">
            {item.agingBucket}
          </span>
        </div>
        <p className="text-sm leading-6 text-slate-300">{item.reason}</p>
      </div>

      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-white">Recommended action</h4>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
          <p className="font-medium uppercase tracking-[0.16em] text-slate-400">{item.recommendedAction.type}</p>
          <p className="mt-2">{item.recommendedAction.reason}</p>
          <p className="mt-2 text-xs text-slate-400">Confidence: {item.recommendedAction.confidence}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-white">Allowed actions</h4>
          <span className="rounded-full border border-white/8 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">
            Server enforced
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {item.allowedActions.map((action) => (
            <span key={action} className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white">
              {action}
            </span>
          ))}
        </div>
        {canMarkInProgress ? (
          <button
            type="button"
            onClick={() => void onMarkInProgress([item.id])}
            disabled={isSubmitting}
            className="rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60 hover:border-white/18 hover:bg-white/[0.09]"
          >
            {isSubmitting ? "Updating..." : "Mark in progress"}
          </button>
        ) : null}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-white">Timeline</h4>
          <span className="text-sm text-slate-500">Projection trace</span>
        </div>
        <div className="space-y-3">
          {item.timeline.map((entry) => (
            <div key={`${entry.at}-${entry.event}`} className="rounded-2xl border border-white/8 bg-black/20 p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-white">{entry.event}</p>
                <span className="text-xs text-slate-500">{formatTimestampLabel(entry.at)}</span>
              </div>
              <p className="mt-1 text-sm text-slate-400">{entry.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function RevenueWorkbench({
  items,
  metrics,
  typeOptions,
  totalItems,
  currentPage,
  pageSize,
  totalPages,
  sortBy,
  sortDirection,
  snapshotNotice,
  onMarkInProgress,
}: {
  items: QueueItem[];
  metrics: InsightMetric[];
  typeOptions: string[];
  totalItems: number;
  currentPage: number;
  pageSize: number;
  totalPages: number;
  sortBy: string;
  sortDirection: string;
  snapshotNotice?: string | null;
  onMarkInProgress: (itemIds: string[]) => Promise<RevenueWorklistActionResponse>;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkFeedback, setBulkFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const typeFilter = searchParams.get("type") ?? ALL_TYPES;
  const priorityFilter = searchParams.get("priority") ?? ALL_PRIORITIES;
  const statusFilter = searchParams.get("status") ?? ALL_STATUSES;
  const searchText = searchParams.get("search") ?? "";
  const selectedId = searchParams.get("selected");
  const activeSortBy = normalizeSortValue(searchParams.get("sort_by") ?? sortBy, normalizeSortValue(sortBy, DEFAULT_SORT_BY));
  const activeSortDirection = normalizeSortDirection(
    searchParams.get("sort_direction") ?? sortDirection,
    normalizeSortDirection(sortDirection, DEFAULT_SORT_DIRECTION),
  );
  const activePage = Number.parseInt(searchParams.get("page") ?? String(currentPage), 10) || currentPage;

  const activeView = useMemo(
    () => getActiveViewLabel({ typeFilter, priorityFilter, statusFilter, searchText }),
    [priorityFilter, searchText, statusFilter, typeFilter],
  );

  const updateQuery = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      const resetPage = Object.keys(updates).some((key) =>
        ["type", "priority", "status", "search", "sort_by", "sort_direction"].includes(key),
      );

      Object.entries(updates).forEach(([key, value]) => {
        const shouldDelete =
          value === null ||
          value === "" ||
          value === ALL_TYPES ||
          value === ALL_PRIORITIES ||
          value === ALL_STATUSES ||
          (key === "sort_by" && value === DEFAULT_SORT_BY) ||
          (key === "sort_direction" && value === DEFAULT_SORT_DIRECTION) ||
          (key === "page" && value === "1");
        if (shouldDelete) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      });

      if (resetPage && !Object.prototype.hasOwnProperty.call(updates, "page")) {
        params.delete("page");
      }
      if (resetPage && !Object.prototype.hasOwnProperty.call(updates, "selected")) {
        params.delete("selected");
      }

      const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
      startTransition(() => {
        router.replace(nextUrl, { scroll: false });
      });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    const nextSelectedId = items[0]?.id ?? null;
    if (items.length === 0) {
      if (selectedId) {
        updateQuery({ selected: null });
      }
      return;
    }
    if (!selectedId || !items.some((item) => item.id === selectedId)) {
      updateQuery({ selected: nextSelectedId });
    }
  }, [items, selectedId, updateQuery]);

  useEffect(() => {
    if (!bulkFeedback) {
      return;
    }
    const timeout = window.setTimeout(() => setBulkFeedback(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [bulkFeedback]);

  const selectedItem = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const hiddenSelectedCount = selectedIds.filter((id) => !items.some((item) => item.id === id)).length;

  async function handleMarkInProgress(itemIds: string[]) {
    if (itemIds.length === 0 || isSubmitting) {
      return {
        action: "mark_in_progress",
        updated_work_item_ids: [],
        updated_count: 0,
        failed_count: 0,
        results: [],
      };
    }

    try {
      setIsSubmitting(true);
      const response = await onMarkInProgress(itemIds);
      const updatedCount = response.updated_count ?? 0;
      const failedCount = response.failed_count ?? 0;
      const failedResults = response.results.filter((result) => result.status !== "completed");
      const firstFailure = failedResults[0]?.error_message?.trim();

      if (updatedCount > 0 && failedCount === 0) {
        setBulkFeedback({
          tone: "success",
          message: `Marked ${updatedCount} work item${updatedCount === 1 ? "" : "s"} in progress.`,
        });
      } else if (updatedCount > 0 && failedCount > 0) {
        setBulkFeedback({
          tone: "success",
          message: `${updatedCount} item${updatedCount === 1 ? "" : "s"} updated, ${failedCount} failed.${firstFailure ? ` ${firstFailure}` : ""}`,
        });
      } else {
        setBulkFeedback({
          tone: "error",
          message: firstFailure || "No selected work items could be updated.",
        });
      }

      const successfulIds = new Set(
        response.results.filter((result) => result.status === "completed").map((result) => result.work_item_id),
      );
      setSelectedIds((current) => current.filter((id) => !successfulIds.has(id)));
      return response;
    } catch (error) {
      setBulkFeedback({
        tone: "error",
        message:
          error instanceof Error && error.message.trim()
            ? error.message
            : "Unable to update the selected work items right now.",
      });
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  }

  function toggleSelect(itemId: string) {
    setSelectedIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleSelectVisible() {
    const visibleIds = items.map((item) => item.id);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
    setSelectedIds((current) =>
      allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds])),
    );
  }

  function applySavedView(view: string) {
    const nextState = getSavedViewState(view);
    updateQuery({
      type: nextState.type ?? null,
      priority: nextState.priority ?? null,
      status: nextState.status ?? null,
      search: nextState.search ?? null,
    });
  }

  function changePage(nextPage: number) {
    if (nextPage < 1 || nextPage > totalPages || nextPage === activePage) {
      return;
    }
    updateQuery({ page: String(nextPage) });
  }

  return (
    <div className="space-y-6">
      <div className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4 backdrop-blur-sm">
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Worklist source</p>
        <div className="mt-3 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <p className="text-sm text-slate-200">Queue rows and summary cards are rendered directly from the backend worklist contract.</p>
          <p className="text-sm text-slate-400">
            Server page {activePage} of {Math.max(totalPages, 1)} · {totalItems} backend work item{totalItems === 1 ? "" : "s"} available.
          </p>
        </div>
        {snapshotNotice ? (
          <p className="mt-3 rounded-2xl border border-amber-500/20 bg-amber-500/[0.08] px-4 py-3 text-sm text-amber-100">
            {snapshotNotice}
          </p>
        ) : null}
      </div>

      <InsightStrip metrics={metrics} />

      <FilterBar
        typeFilter={typeFilter}
        priorityFilter={priorityFilter}
        statusFilter={statusFilter}
        searchText={searchText}
        sortBy={activeSortBy}
        sortDirection={activeSortDirection}
        typeOptions={typeOptions}
        activeView={activeView}
        onTypeChange={(value) => updateQuery({ type: value })}
        onPriorityChange={(value) => updateQuery({ priority: value })}
        onStatusChange={(value) => updateQuery({ status: value })}
        onSearchChange={(value) => updateQuery({ search: value })}
        onSortByChange={(value) => updateQuery({ sort_by: value })}
        onSortDirectionChange={(value) => updateQuery({ sort_direction: value })}
        onApplySavedView={applySavedView}
      />

      <BulkActionBar
        selectedCount={selectedIds.length}
        hiddenSelectedCount={hiddenSelectedCount}
        isSubmitting={isSubmitting}
        onMarkInProgress={() => void handleMarkInProgress(selectedIds)}
        onClearSelection={() => setSelectedIds([])}
      />

      {bulkFeedback ? (
        <div
          className={`rounded-[20px] px-4 py-3 text-sm ${
            bulkFeedback.tone === "success"
              ? "border border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-100"
              : "border border-rose-400/20 bg-rose-400/[0.08] text-rose-100"
          }`}
        >
          {bulkFeedback.message}
        </div>
      ) : null}

      <PaginationBar
        currentPage={activePage}
        totalPages={Math.max(totalPages, 1)}
        totalItems={totalItems}
        pageSize={pageSize}
        visibleCount={items.length}
        onPageChange={changePage}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)_minmax(320px,0.9fr)]">
        <WorkQueueTable
          items={items}
          selectedId={selectedItem?.id ?? null}
          selectedIds={selectedIds}
          onSelect={(item) => updateQuery({ selected: item.id })}
          onToggleSelect={toggleSelect}
          onToggleSelectVisible={toggleSelectVisible}
        />
        <ClaimDrawer item={selectedItem} />
        <DecisionSupportPanel item={selectedItem} isSubmitting={isSubmitting} onMarkInProgress={handleMarkInProgress} />
      </div>
    </div>
  );
}

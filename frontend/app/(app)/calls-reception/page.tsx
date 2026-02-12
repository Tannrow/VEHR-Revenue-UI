"use client";

import { useEffect, useMemo, useState } from "react";

import { getBrowserAccessToken } from "@/lib/auth";
import { ApiError, apiFetch, apiFetchBlob, buildUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";

type CallRow = {
  call_id: string;
  session_id?: string | null;
  state: string;
  missed?: boolean;
  call_date?: string | null;
  disposition?: string | null;
  from_number?: string | null;
  to_number?: string | null;
  direction?: string | null;
  extension_id?: string | null;
  started_at?: string | null;
  answered_at?: string | null;
  ended_at?: string | null;
  last_event_at: string;
  overlay_status: "NEW" | "MISSED" | "CALLED_BACK" | "RESOLVED";
  assigned_to_user_id?: string | null;
  notes?: string | null;
};

type SnapshotResponse = {
  call_log: CallRow[];
  subscription_status: string;
};

type DispositionResponse = {
  call_id: string;
  status: "NEW" | "MISSED" | "CALLED_BACK" | "RESOLVED";
  assigned_to_user_id?: string | null;
  notes?: string | null;
  updated_at: string;
};

type CallEventPayload = {
  call_id: string;
  session_id?: string | null;
  state: string;
  missed?: boolean;
  call_date?: string | null;
  disposition?: string | null;
  from_number?: string | null;
  to_number?: string | null;
  direction?: string | null;
  extension_id?: string | null;
  started_at?: string | null;
  answered_at?: string | null;
  ended_at?: string | null;
  overlay_status?: "NEW" | "MISSED" | "CALLED_BACK" | "RESOLVED";
  assigned_to_user_id?: string | null;
  notes?: string | null;
  received_at?: string | null;
};

type DispositionEventPayload = {
  call_id: string;
  status: "NEW" | "MISSED" | "CALLED_BACK" | "RESOLVED";
  assigned_to_user_id?: string | null;
  notes?: string | null;
};

type StatusMeta = {
  label: "Completed" | "In progress" | "On hold" | "Blocked/Missed";
  className: string;
};

const WORKFLOW_OPTIONS = ["NEW", "MISSED", "CALLED_BACK", "RESOLVED"] as const;
const ACTIVE_STATES = new Set(["ringing", "answered", "connected", "in_progress", "on_call"]);
const HOLD_STATES = new Set(["hold", "on_hold", "held"]);

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function safeDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function todayLocalDate(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function formatDateTime(value: string | null | undefined): string {
  const parsed = safeDate(value);
  if (!parsed) return "n/a";
  return parsed.toLocaleString();
}

function formatDisplayDate(value: string | null | undefined): string {
  const parsed = safeDate(value);
  if (!parsed) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function formatDirection(direction: string | null | undefined): string {
  const normalized = (direction || "").trim().toLowerCase();
  if (!normalized) return "Unknown";
  if (normalized === "inbound") return "Inbound";
  if (normalized === "outbound") return "Outbound";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function resolveCallerName(row: CallRow): string {
  const candidate = (row as CallRow & { caller_name?: string | null }).caller_name;
  if (candidate && candidate.trim()) return candidate.trim();
  return "Unknown";
}

function formatDuration(totalMs: number): string {
  const safe = Math.max(0, Math.floor(totalMs / 1000));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function isAnsweredCall(row: CallRow): boolean {
  if (row.answered_at) return true;
  if (row.overlay_status === "CALLED_BACK" || row.overlay_status === "RESOLVED") return true;
  return ["answered", "connected", "in_progress", "on_call"].includes(row.state.trim().toLowerCase());
}

function isMissedUnresolved(row: CallRow): boolean {
  const unresolved = row.overlay_status !== "CALLED_BACK" && row.overlay_status !== "RESOLVED";
  return unresolved && Boolean(row.missed || row.overlay_status === "MISSED");
}

function getStatusMeta(row: CallRow): StatusMeta {
  const state = row.state.trim().toLowerCase();
  if (isMissedUnresolved(row)) {
    return { label: "Blocked/Missed", className: "bg-rose-600" };
  }
  if (HOLD_STATES.has(state)) {
    return { label: "On hold", className: "bg-amber-500" };
  }
  if (!row.ended_at && ACTIVE_STATES.has(state)) {
    return { label: "In progress", className: "bg-blue-600" };
  }
  if (isAnsweredCall(row)) {
    return { label: "Completed", className: "bg-emerald-600" };
  }
  return { label: "In progress", className: "bg-blue-600" };
}

function formatCallTime(row: CallRow, nowMs: number): string {
  const started = safeDate(row.started_at);
  if (!started) return "--";
  const ended = safeDate(row.ended_at);
  if (ended) {
    return formatDuration(ended.getTime() - started.getTime());
  }
  return `LIVE ${formatDuration(nowMs - started.getTime())}`;
}

function upsertCall(calls: CallRow[], incoming: Partial<CallRow> & { call_id: string }): CallRow[] {
  const index = calls.findIndex((item) => item.call_id === incoming.call_id);
  const existing = index >= 0 ? calls[index] : null;
  const merged: CallRow = {
    call_id: incoming.call_id,
    session_id: incoming.session_id ?? existing?.session_id ?? null,
    state: incoming.state || existing?.state || "unknown",
    missed: incoming.missed ?? existing?.missed ?? false,
    call_date: incoming.call_date ?? existing?.call_date ?? null,
    disposition: incoming.disposition ?? existing?.disposition ?? null,
    from_number: incoming.from_number ?? existing?.from_number ?? null,
    to_number: incoming.to_number ?? existing?.to_number ?? null,
    direction: incoming.direction ?? existing?.direction ?? null,
    extension_id: incoming.extension_id ?? existing?.extension_id ?? null,
    started_at: incoming.started_at ?? existing?.started_at ?? null,
    answered_at: incoming.answered_at ?? existing?.answered_at ?? null,
    ended_at: incoming.ended_at ?? existing?.ended_at ?? null,
    last_event_at: incoming.last_event_at ?? existing?.last_event_at ?? new Date().toISOString(),
    overlay_status: incoming.overlay_status ?? existing?.overlay_status ?? "NEW",
    assigned_to_user_id: incoming.assigned_to_user_id ?? existing?.assigned_to_user_id ?? null,
    notes: incoming.notes ?? existing?.notes ?? null,
  };

  if (index >= 0) {
    const next = [...calls];
    next[index] = merged;
    return next;
  }
  return [merged, ...calls];
}

export default function CallsReceptionPage() {
  const todayDate = useMemo(() => todayLocalDate(), []);
  const [nowMs, setNowMs] = useState(Date.now());
  const [callLog, setCallLog] = useState<CallRow[]>([]);
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(todayDate);
  const [workflowStatus, setWorkflowStatus] =
    useState<(typeof WORKFLOW_OPTIONS)[number]>("NEW");
  const [workflowNote, setWorkflowNote] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] = useState("MISSING");
  const [streamStatus, setStreamStatus] = useState("connecting");
  const [isLoading, setIsLoading] = useState(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isSavingDisposition, setIsSavingDisposition] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const isHistorical = selectedDate !== todayDate;

  const selectedCall = useMemo(
    () => callLog.find((row) => row.call_id === selectedCallId) ?? null,
    [callLog, selectedCallId],
  );

  useEffect(() => {
    const interval = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedCall) {
      setWorkflowStatus("NEW");
      setWorkflowNote("");
      return;
    }
    setWorkflowStatus(selectedCall.overlay_status);
    setWorkflowNote(selectedCall.notes || "");
  }, [selectedCall]);

  useEffect(() => {
    let mounted = true;
    async function loadSnapshot() {
      setIsLoading(true);
      setError(null);
      try {
        const snapshot = await apiFetch<SnapshotResponse>(`/api/v1/call-center/snapshot?date=${encodeURIComponent(selectedDate)}`, {
          cache: "no-store",
        });
        if (!mounted) return;
        setCallLog(snapshot.call_log);
        setSubscriptionStatus(snapshot.subscription_status);
        setSelectedCallId((current) => {
          if (current && snapshot.call_log.some((item) => item.call_id === current)) return current;
          return snapshot.call_log[0]?.call_id ?? null;
        });
      } catch (loadError) {
        if (!mounted) return;
        setError(toMessage(loadError, "Unable to load call center snapshot."));
      } finally {
        if (mounted) setIsLoading(false);
      }
    }
    void loadSnapshot();
    return () => {
      mounted = false;
    };
  }, [selectedDate]);

  useEffect(() => {
    if (isHistorical) {
      setStreamStatus("historical");
      return;
    }
    const token = getBrowserAccessToken();
    if (!token) {
      setStreamStatus("offline");
      return;
    }
    const streamUrl = `${buildUrl("/api/v1/call-center/stream")}?access_token=${encodeURIComponent(token)}`;
    const source = new EventSource(streamUrl, { withCredentials: true });
    setStreamStatus("connecting");

    source.addEventListener("open", () => {
      setStreamStatus("connected");
    });

    source.addEventListener("call", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as CallEventPayload;
      setCallLog((current) =>
        upsertCall(current, {
          call_id: payload.call_id,
          session_id: payload.session_id ?? null,
          state: payload.state,
          missed: payload.missed ?? payload.state === "missed",
          call_date: payload.call_date ?? null,
          disposition: payload.disposition,
          from_number: payload.from_number,
          to_number: payload.to_number,
          direction: payload.direction,
          extension_id: payload.extension_id,
          started_at: payload.started_at,
          answered_at: payload.answered_at,
          ended_at: payload.ended_at,
          overlay_status: payload.overlay_status,
          assigned_to_user_id: payload.assigned_to_user_id,
          notes: payload.notes,
          last_event_at: payload.received_at ?? new Date().toISOString(),
        }),
      );
      setSelectedCallId((current) => current || payload.call_id);
    });

    source.addEventListener("disposition", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as DispositionEventPayload;
      setCallLog((current) =>
        upsertCall(current, {
          call_id: payload.call_id,
          overlay_status: payload.status,
          assigned_to_user_id: payload.assigned_to_user_id,
          notes: payload.notes,
          last_event_at: new Date().toISOString(),
        }),
      );
    });

    source.addEventListener("snapshot", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as SnapshotResponse;
      setCallLog(payload.call_log);
      setSubscriptionStatus(payload.subscription_status);
    });

    source.onerror = () => {
      setStreamStatus("reconnecting");
    };

    return () => {
      source.close();
      setStreamStatus("offline");
    };
  }, [isHistorical]);

  async function handleExportCsv() {
    setIsExporting(true);
    setError(null);
    try {
      const blob = await apiFetchBlob(`/api/v1/call-center/export?date=${encodeURIComponent(selectedDate)}`, {
        cache: "no-store",
      });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `call-center-${selectedDate}.csv`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (exportError) {
      setError(toMessage(exportError, "Unable to export CSV."));
    } finally {
      setIsExporting(false);
    }
  }

  async function handleSaveDisposition() {
    if (!selectedCall) return;
    setIsSavingDisposition(true);
    setError(null);
    setMessage(null);
    try {
      const response = await apiFetch<DispositionResponse>(
        `/api/v1/call-center/calls/${encodeURIComponent(selectedCall.call_id)}/disposition`,
        {
          method: "POST",
          body: JSON.stringify({
            status: workflowStatus,
            notes: workflowNote || null,
            assigned_to_user_id: selectedCall.assigned_to_user_id || null,
          }),
        },
      );
      setCallLog((current) =>
        upsertCall(current, {
          call_id: response.call_id,
          overlay_status: response.status,
          assigned_to_user_id: response.assigned_to_user_id,
          notes: response.notes,
          last_event_at: response.updated_at,
        }),
      );
      setMessage("Disposition saved.");
    } catch (saveError) {
      setError(toMessage(saveError, "Unable to save disposition."));
    } finally {
      setIsSavingDisposition(false);
    }
  }

  return (
    <div className="space-y-4" data-testid="call-center-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600 text-white">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <path d="M22 16.9v3a2 2 0 0 1-2.2 2A19.9 19.9 0 0 1 11 18.6 19.5 19.5 0 0 1 5.4 13 19.9 19.9 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7 12.9 12.9 0 0 0 .7 2.8 2 2 0 0 1-.5 2.1L8 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5 12.9 12.9 0 0 0 2.8.7A2 2 0 0 1 22 16.9Z" />
            </svg>
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900" data-testid="call-center-title">Call Center</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-600" htmlFor="call_center_date">
            Date
          </label>
          <input
            id="call_center_date"
            type="date"
            className="h-9 rounded border border-slate-300 bg-white px-3 text-sm"
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            className="h-9 rounded px-3"
            onClick={() => void handleExportCsv()}
            disabled={isExporting}
          >
            {isExporting ? "Exporting..." : "Export CSV"}
          </Button>
        </div>
      </div>

      <p className="text-xs text-slate-600">
        Stream: {streamStatus} | Subscription: {subscriptionStatus}
        {isHistorical ? " | Historical view (stream disabled)" : ""}
      </p>
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="text-sm text-slate-700">{message}</p> : null}

      <div className="overflow-x-auto border border-slate-300 bg-white">
        <table className="min-w-[980px] w-full table-fixed border-collapse text-center text-sm text-slate-800">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Date</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Caller</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Phone #</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Direction</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Answered?</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Status</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Call Time</th>
              <th className="border border-slate-300 px-2 py-2 font-semibold">Notes</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="border border-slate-200 px-3 py-5 text-slate-500" colSpan={8}>
                  Loading call center...
                </td>
              </tr>
            ) : null}
            {!isLoading && callLog.length === 0 ? (
              <tr>
                <td className="border border-slate-200 px-3 py-5 text-slate-500" colSpan={8}>
                  No calls for this date.
                </td>
              </tr>
            ) : null}
            {!isLoading
              ? callLog.map((row) => {
                  const status = getStatusMeta(row);
                  const isSelected = selectedCallId === row.call_id;
                  return (
                    <tr
                      key={row.call_id}
                      className={`cursor-pointer ${isSelected ? "bg-sky-50" : "bg-white hover:bg-slate-50"}`}
                      onClick={() => {
                        setSelectedCallId(row.call_id);
                        setIsDrawerOpen(true);
                      }}
                    >
                      <td className="border border-slate-200 px-2 py-2">{formatDisplayDate(row.started_at || row.last_event_at)}</td>
                      <td className="border border-slate-200 px-2 py-2">{resolveCallerName(row)}</td>
                      <td className="border border-slate-200 px-2 py-2">{row.from_number || "Unknown"}</td>
                      <td className="border border-slate-200 px-2 py-2">{formatDirection(row.direction)}</td>
                      <td className="border border-slate-200 px-2 py-2">{isAnsweredCall(row) ? "Yes" : "No"}</td>
                      <td className={`border border-slate-200 px-2 py-2 font-semibold text-white ${status.className}`}>{status.label}</td>
                      <td className="border border-slate-200 px-2 py-2 font-mono">{formatCallTime(row, nowMs)}</td>
                      <td className="border border-slate-200 px-2 py-2">{row.notes || ""}</td>
                    </tr>
                  );
                })
              : null}
          </tbody>
        </table>
      </div>

      {isDrawerOpen && selectedCall ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 bg-slate-900/35"
            aria-label="Close details drawer"
            onClick={() => setIsDrawerOpen(false)}
          />
          <aside className="fixed right-0 top-0 z-40 h-full w-full max-w-md overflow-y-auto border-l border-slate-300 bg-white p-5 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-900">Call Details</h2>
              <button
                type="button"
                className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-600 hover:bg-slate-100"
                onClick={() => setIsDrawerOpen(false)}
              >
                Close
              </button>
            </div>

            <div className="mt-4 space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2 border border-slate-200 bg-slate-50 p-3">
                <p className="font-semibold text-slate-700">Call ID</p>
                <p className="truncate text-slate-800">{selectedCall.call_id}</p>
                <p className="font-semibold text-slate-700">Session</p>
                <p className="truncate text-slate-800">{selectedCall.session_id || "n/a"}</p>
                <p className="font-semibold text-slate-700">Phone #</p>
                <p className="text-slate-800">{selectedCall.from_number || "Unknown"}</p>
                <p className="font-semibold text-slate-700">Direction</p>
                <p className="text-slate-800">{formatDirection(selectedCall.direction)}</p>
                <p className="font-semibold text-slate-700">State</p>
                <p className="text-slate-800">{selectedCall.state}</p>
                <p className="font-semibold text-slate-700">Started</p>
                <p className="text-slate-800">{formatDateTime(selectedCall.started_at)}</p>
                <p className="font-semibold text-slate-700">Answered</p>
                <p className="text-slate-800">{formatDateTime(selectedCall.answered_at)}</p>
                <p className="font-semibold text-slate-700">Ended</p>
                <p className="text-slate-800">{formatDateTime(selectedCall.ended_at)}</p>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-600" htmlFor="workflow_status">
                  Disposition
                </label>
                <select
                  id="workflow_status"
                  className="h-10 w-full rounded border border-slate-300 bg-white px-3 text-sm disabled:cursor-not-allowed disabled:bg-slate-100"
                  value={workflowStatus}
                  onChange={(event) => setWorkflowStatus(event.target.value as (typeof WORKFLOW_OPTIONS)[number])}
                  disabled={isHistorical}
                >
                  {WORKFLOW_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-600" htmlFor="workflow_note">
                  Notes
                </label>
                <textarea
                  id="workflow_note"
                  className="min-h-32 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:bg-slate-100"
                  value={workflowNote}
                  onChange={(event) => setWorkflowNote(event.target.value)}
                  disabled={isHistorical}
                />
              </div>

              <Button
                type="button"
                className="h-10 w-full rounded"
                onClick={() => void handleSaveDisposition()}
                disabled={isSavingDisposition || isHistorical}
              >
                {isHistorical ? "Historical view (read-only)" : (isSavingDisposition ? "Saving..." : "Save disposition")}
              </Button>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}

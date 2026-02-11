"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type PresenceItem = {
  user_id: string;
  full_name?: string | null;
  email: string;
  role: string;
  status: "available" | "on_call" | "offline";
  source: string;
};

type PresenceResponse = {
  items: PresenceItem[];
};

type CallRow = {
  id: string;
  event_type: string;
  rc_event_id?: string | null;
  session_id?: string | null;
  call_id?: string | null;
  from_number?: string | null;
  to_number?: string | null;
  direction?: string | null;
  disposition?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at: string;
  workflow_status?: string | null;
  note?: string | null;
  handled_by_user_id?: string | null;
  handled_by_name?: string | null;
  followup_task_id?: string | null;
};

type WorkflowResponse = {
  id: string;
  ringcentral_event_id: string;
  workflow_status: string;
  note?: string | null;
  handled_by_user_id?: string | null;
  followup_task_id?: string | null;
  updated_at: string;
};

type FollowupResponse = {
  task_id: string;
  ringcentral_event_id: string;
  workflow_id: string;
};

const WORKFLOW_OPTIONS = [
  "missed",
  "callback_attempted",
  "callback_completed",
  "voicemail_left",
  "scheduled",
  "closed",
] as const;
type WorkflowStatus = (typeof WORKFLOW_OPTIONS)[number];

const CALL_WRITE_ROLES = new Set([
  "admin",
  "office_manager",
  "counselor",
  "sud_supervisor",
  "case_manager",
  "receptionist",
]);

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "n/a";
  }
  return parsed.toLocaleString();
}

function normalizeDisposition(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}

function statusDotClass(status: PresenceItem["status"]): string {
  if (status === "on_call") {
    return "bg-rose-500";
  }
  if (status === "available") {
    return "bg-emerald-500";
  }
  return "bg-slate-400";
}

function callStatusBadge(disposition: string | null | undefined): string {
  const normalized = normalizeDisposition(disposition);
  if (normalized === "missed") {
    return "ui-status-error";
  }
  if (normalized === "answered" || normalized === "connected") {
    return "ui-status-success";
  }
  return "ui-status-warning";
}

export default function CallsReceptionPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [presence, setPresence] = useState<PresenceItem[]>([]);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [filter, setFilter] = useState<"all" | "missed" | "answered">("all");
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState<WorkflowStatus>("missed");
  const [workflowNote, setWorkflowNote] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSavingWorkflow, setIsSavingWorkflow] = useState(false);
  const [isCreatingFollowup, setIsCreatingFollowup] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canEdit = useMemo(() => {
    return currentUser ? CALL_WRITE_ROLES.has(currentUser.role) : false;
  }, [currentUser]);

  const selectedCall = useMemo(
    () => calls.find((row) => row.id === selectedCallId) ?? null,
    [calls, selectedCallId],
  );

  const filteredCalls = useMemo(() => {
    if (filter === "all") {
      return calls;
    }
    if (filter === "missed") {
      return calls.filter((row) => normalizeDisposition(row.disposition) === "missed");
    }
    return calls.filter((row) => {
      const value = normalizeDisposition(row.disposition);
      return value === "answered" || value === "connected";
    });
  }, [calls, filter]);

  const loadReceptionData = useCallback(async ({ showSpinner }: { showSpinner: boolean }) => {
    if (showSpinner) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setError(null);

    try {
      const [me, presenceRes, callsRes] = await Promise.all([
        apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
        apiFetch<PresenceResponse>("/api/v1/reception/presence", { cache: "no-store" }),
        apiFetch<CallRow[]>("/api/v1/reception/calls", { cache: "no-store" }),
      ]);
      setCurrentUser(me);
      setPresence(presenceRes.items);
      setCalls(callsRes);

      if (!selectedCallId && callsRes[0]) {
        setSelectedCallId(callsRes[0].id);
      }
      if (selectedCallId && !callsRes.find((row) => row.id === selectedCallId) && callsRes[0]) {
        setSelectedCallId(callsRes[0].id);
      }
    } catch (loadError) {
      setError(toMessage(loadError, "Unable to load reception data."));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [selectedCallId]);

  useEffect(() => {
    void loadReceptionData({ showSpinner: true });
    const timer = window.setInterval(() => {
      void loadReceptionData({ showSpinner: false });
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadReceptionData]);

  useEffect(() => {
    if (!selectedCall) {
      setWorkflowStatus("missed");
      setWorkflowNote("");
      return;
    }
    const nextStatus = (selectedCall.workflow_status || "missed") as WorkflowStatus;
    setWorkflowStatus(WORKFLOW_OPTIONS.includes(nextStatus) ? nextStatus : "missed");
    setWorkflowNote(selectedCall.note || "");
  }, [selectedCall]);

  async function handleSaveWorkflow() {
    if (!selectedCall) {
      return;
    }
    setIsSavingWorkflow(true);
    setMessage(null);
    setError(null);
    try {
      const response = await apiFetch<WorkflowResponse>(
        `/api/v1/reception/calls/${encodeURIComponent(selectedCall.id)}/workflow`,
        {
          method: "PATCH",
          body: JSON.stringify({
            workflow_status: workflowStatus,
            note: workflowNote || null,
          }),
        },
      );
      setCalls((current) =>
        current.map((row) =>
          row.id === selectedCall.id
            ? {
                ...row,
                workflow_status: response.workflow_status,
                note: response.note,
                handled_by_user_id: response.handled_by_user_id,
                followup_task_id: response.followup_task_id,
              }
            : row,
        ),
      );
      setMessage("Workflow updated.");
    } catch (saveError) {
      setError(toMessage(saveError, "Unable to update workflow."));
    } finally {
      setIsSavingWorkflow(false);
    }
  }

  async function handleCreateFollowup() {
    if (!selectedCall) {
      return;
    }
    setIsCreatingFollowup(true);
    setMessage(null);
    setError(null);
    try {
      const response = await apiFetch<FollowupResponse>(
        `/api/v1/reception/calls/${encodeURIComponent(selectedCall.id)}/followup`,
        {
          method: "POST",
          body: JSON.stringify({
            note: workflowNote || null,
          }),
        },
      );
      setCalls((current) =>
        current.map((row) =>
          row.id === selectedCall.id
            ? {
                ...row,
                followup_task_id: response.task_id,
                workflow_status: row.workflow_status || "callback_attempted",
              }
            : row,
        ),
      );
      setMessage("Follow-up task created.");
    } catch (followupError) {
      setError(toMessage(followupError, "Unable to create follow-up task."));
    } finally {
      setIsCreatingFollowup(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Work</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Calls & Reception</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Live call feed and workflow tracking for reception follow-through.
        </p>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="text-sm text-slate-700">{message}</p> : null}

      {isLoading ? <p className="text-sm text-slate-600">Loading calls and presence...</p> : null}

      {!isLoading ? (
        <div className="grid gap-5 xl:grid-cols-[300px_1.4fr_1fr]">
          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">Staff Presence</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {presence.length === 0 ? (
                <p className="text-sm text-slate-500">No staff presence available.</p>
              ) : (
                presence.map((item) => (
                  <div key={item.user_id} className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${statusDotClass(item.status)}`} />
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {item.full_name || item.email}
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.status.replace("_", " ")} · {item.role}
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="bg-white shadow-sm">
            <CardHeader className="gap-2 pb-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-xl text-slate-900">Call Feed</CardTitle>
                <div className="flex items-center gap-2">
                  <select
                    value={filter}
                    onChange={(event) => setFilter(event.target.value as "all" | "missed" | "answered")}
                    className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                  >
                    <option value="all">All calls</option>
                    <option value="missed">Missed</option>
                    <option value="answered">Answered</option>
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 rounded-lg px-3"
                    onClick={() => void loadReceptionData({ showSpinner: false })}
                    disabled={isRefreshing}
                  >
                    {isRefreshing ? "Refreshing..." : "Refresh"}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {filteredCalls.length === 0 ? (
                <p className="text-sm text-slate-500">No calls for this filter.</p>
              ) : (
                filteredCalls.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                      selectedCallId === row.id
                        ? "border-sky-300 bg-sky-50"
                        : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                    }`}
                    onClick={() => setSelectedCallId(row.id)}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-900">
                        {row.from_number || "Unknown"} → {row.to_number || "Unknown"}
                      </p>
                      <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${callStatusBadge(row.disposition)}`}>
                        {row.disposition || "unknown"}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatDateTime(row.started_at || row.created_at)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Workflow: {row.workflow_status || "not set"}
                    </p>
                  </button>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">Call Detail</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-0">
              {!selectedCall ? (
                <p className="text-sm text-slate-500">Select a call to review details.</p>
              ) : (
                <>
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <p className="font-semibold text-slate-900">
                      {selectedCall.from_number || "Unknown"} → {selectedCall.to_number || "Unknown"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Disposition: {selectedCall.disposition || "unknown"}
                    </p>
                    <p className="text-xs text-slate-500">
                      Started: {formatDateTime(selectedCall.started_at || selectedCall.created_at)}
                    </p>
                    <p className="text-xs text-slate-500">
                      Ended: {formatDateTime(selectedCall.ended_at)}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="workflow_status">
                      Workflow status
                    </label>
                    <select
                      id="workflow_status"
                      className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                      value={workflowStatus}
                      onChange={(event) => setWorkflowStatus(event.target.value as WorkflowStatus)}
                      disabled={!canEdit}
                    >
                      {WORKFLOW_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {value.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="workflow_note">
                      Note
                    </label>
                    <textarea
                      id="workflow_note"
                      className="min-h-24 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
                      value={workflowNote}
                      onChange={(event) => setWorkflowNote(event.target.value)}
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      className="h-9 rounded-lg px-3"
                      onClick={() => void handleSaveWorkflow()}
                      disabled={!canEdit || isSavingWorkflow}
                    >
                      {isSavingWorkflow ? "Saving..." : "Save workflow"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-9 rounded-lg px-3"
                      onClick={() => void handleSaveWorkflow()}
                      disabled={!canEdit || isSavingWorkflow}
                    >
                      Add Call Note
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-9 rounded-lg px-3"
                      onClick={() => void handleCreateFollowup()}
                      disabled={!canEdit || isCreatingFollowup}
                    >
                      {isCreatingFollowup ? "Creating..." : "Create follow-up task"}
                    </Button>
                  </div>

                  {selectedCall.followup_task_id ? (
                    <p className="text-xs text-slate-500">
                      Linked follow-up task: {selectedCall.followup_task_id}
                    </p>
                  ) : null}

                  {!canEdit ? (
                    <p className="text-xs text-slate-500">
                      You have read-only access for reception workflows.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

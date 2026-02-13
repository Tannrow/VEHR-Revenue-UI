"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import {
  bulkTaskUpdate,
  completeTask,
  createTask,
  getTask,
  listTasks,
  reopenTask,
  taskDueBucket,
  taskPermissionsForRole,
  updateTask,
  type TaskPriority,
  type TaskRecord,
  type TaskScope,
  type TaskStatus,
} from "@/lib/tasks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type TeamMember = {
  id: string;
  full_name?: string | null;
  email: string;
};

type TeamRow = {
  name: string;
  members: TeamMember[];
};

type ViewPreset = "my" | "team" | "overdue" | "external";
type StatusFilter = "active" | "all" | TaskStatus;
type BulkAction = "complete" | "assign" | "due_date";

type TaskFormState = {
  title: string;
  description: string;
  dueAtLocal: string;
  priority: TaskPriority;
  assignedToUserId: string;
};

const DEFAULT_CREATE_FORM: TaskFormState = {
  title: "",
  description: "",
  dueAtLocal: "",
  priority: "normal",
  assignedToUserId: "",
};

const VIEW_LABELS: Record<ViewPreset, string> = {
  my: "My Tasks",
  team: "Team Tasks",
  overdue: "Overdue",
  external: "Waiting on External",
};

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function toIsoOrNull(localDateTime: string): string | null {
  if (!localDateTime) {
    return null;
  }
  const asDate = new Date(localDateTime);
  if (Number.isNaN(asDate.getTime())) {
    return null;
  }
  return asDate.toISOString();
}

function toLocalInputValue(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const asDate = new Date(value);
  if (Number.isNaN(asDate.getTime())) {
    return "";
  }
  const year = asDate.getFullYear();
  const month = `${asDate.getMonth() + 1}`.padStart(2, "0");
  const day = `${asDate.getDate()}`.padStart(2, "0");
  const hour = `${asDate.getHours()}`.padStart(2, "0");
  const minute = `${asDate.getMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function formatDueAt(dueAt: string | null | undefined): string {
  if (!dueAt) {
    return "No due date";
  }
  const asDate = new Date(dueAt);
  if (Number.isNaN(asDate.getTime())) {
    return "No due date";
  }
  return asDate.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatStatus(status: TaskStatus): string {
  if (status === "in_progress") {
    return "In Progress";
  }
  if (status === "done") {
    return "Done";
  }
  if (status === "canceled") {
    return "Canceled";
  }
  return "Open";
}

function formatPriority(priority: TaskPriority): string {
  if (priority === "urgent") return "Urgent";
  if (priority === "high") return "High";
  if (priority === "low") return "Low";
  return "Normal";
}

function statusBadgeClass(task: TaskRecord): string {
  if (task.status === "done") {
    return "ui-status-success";
  }
  if (task.status === "canceled") {
    return "ui-status-info";
  }
  const bucket = taskDueBucket(task.due_at);
  if (bucket === "overdue") {
    return "ui-status-error";
  }
  if (bucket === "today") {
    return "ui-status-warning";
  }
  return "ui-status-info";
}

function canUseView(view: ViewPreset, canReadTeam: boolean): boolean {
  if (view === "team") {
    return canReadTeam;
  }
  return true;
}

function scopeForView(
  view: ViewPreset,
  canReadTeam: boolean,
  forceAll: boolean,
  canReadAll: boolean,
): TaskScope {
  if (forceAll && canReadAll) {
    return "all";
  }
  if (view === "team" || view === "overdue" || view === "external") {
    return canReadTeam ? "team" : "self";
  }
  return "self";
}

function dueForView(view: ViewPreset): "overdue" | "none" | undefined {
  if (view === "overdue") {
    return "overdue";
  }
  if (view === "external") {
    return "none";
  }
  return undefined;
}

function statusesForFilter(statusFilter: StatusFilter): TaskStatus[] | undefined {
  if (statusFilter === "all") {
    return undefined;
  }
  if (statusFilter === "active") {
    return ["open", "in_progress"];
  }
  return [statusFilter];
}

export default function TasksPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);

  const [activeView, setActiveView] = useState<ViewPreset>("my");
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");

  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<TaskRecord | null>(null);
  const [detailDraft, setDetailDraft] = useState<TaskFormState | null>(null);
  const [detailStatus, setDetailStatus] = useState<TaskStatus>("open");

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<TaskFormState>(DEFAULT_CREATE_FORM);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSavingCreate, setIsSavingCreate] = useState(false);

  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [bulkAction, setBulkAction] = useState<BulkAction>("complete");
  const [bulkAssignee, setBulkAssignee] = useState("");
  const [bulkDueLocal, setBulkDueLocal] = useState("");
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [isApplyingBulk, setIsApplyingBulk] = useState(false);

  const taskPermissions = useMemo(
    () => taskPermissionsForRole(currentUser?.role),
    [currentUser?.role],
  );

  const effectiveScope = useMemo(
    () =>
      scopeForView(
        activeView,
        taskPermissions.canReadTeam,
        showAllTasks,
        taskPermissions.canReadAll,
      ),
    [activeView, showAllTasks, taskPermissions.canReadAll, taskPermissions.canReadTeam],
  );

  const effectiveDueFilter = useMemo(() => dueForView(activeView), [activeView]);

  useEffect(() => {
    let isMounted = true;

    async function loadContext() {
      try {
        const me = await apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" });
        if (!isMounted) {
          return;
        }
        setCurrentUser(me);
      } catch {
        if (!isMounted) {
          return;
        }
        setCurrentUser(null);
      }
    }

    void loadContext();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    const me = currentUser;

    let isMounted = true;

    async function loadTeamMembers() {
      try {
        const rows = await apiFetch<TeamRow[]>("/api/v1/staff/teams", { cache: "no-store" });
        if (!isMounted) {
          return;
        }
        const byId = new Map<string, TeamMember>();
        for (const row of rows) {
          for (const member of row.members) {
            if (!byId.has(member.id)) {
              byId.set(member.id, member);
            }
          }
        }
        if (!byId.has(me.id)) {
          byId.set(me.id, {
            id: me.id,
            full_name: me.full_name,
            email: me.email,
          });
        }
        setTeamMembers(Array.from(byId.values()));
      } catch {
        if (!isMounted) {
          return;
        }
        setTeamMembers([
          {
            id: me.id,
            full_name: me.full_name,
            email: me.email,
          },
        ]);
      }
    }

    void loadTeamMembers();
    return () => {
      isMounted = false;
    };
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    let isMounted = true;

    async function loadTasks() {
      setIsLoading(true);
      setError(null);

      try {
        const result = await listTasks({
          scope: effectiveScope,
          due: effectiveDueFilter,
          search: search.trim() || undefined,
          status: statusesForFilter(statusFilter),
          limit: 200,
        });
        if (!isMounted) {
          return;
        }
        setTasks(result.items);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        setError(toMessage(loadError, "Unable to load tasks."));
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadTasks();
    return () => {
      isMounted = false;
    };
  }, [currentUser, effectiveDueFilter, effectiveScope, refreshToken, search, statusFilter]);

  useEffect(() => {
    if (!selectedTaskId) {
      setSelectedTask(null);
      setDetailDraft(null);
      return;
    }
    const taskId = selectedTaskId;

    let isMounted = true;

    async function loadTaskDetail() {
      try {
        const task = await getTask(taskId);
        if (!isMounted) {
          return;
        }
        setSelectedTask(task);
        setDetailStatus(task.status);
        setDetailDraft({
          title: task.title,
          description: task.description ?? "",
          dueAtLocal: toLocalInputValue(task.due_at),
          priority: task.priority,
          assignedToUserId: task.assigned_to_user_id ?? "",
        });
      } catch (detailError) {
        if (!isMounted) {
          return;
        }
        setError(toMessage(detailError, "Unable to load task detail."));
      }
    }

    void loadTaskDetail();
    return () => {
      isMounted = false;
    };
  }, [selectedTaskId, refreshToken]);

  useEffect(() => {
    setSelectedIds({});
  }, [tasks]);

  useEffect(() => {
    if (!canUseView(activeView, taskPermissions.canReadTeam)) {
      setActiveView("my");
    }
  }, [activeView, taskPermissions.canReadTeam]);

  const selectedTaskCount = useMemo(
    () => Object.values(selectedIds).filter(Boolean).length,
    [selectedIds],
  );

  const assigneeOptions = useMemo(
    () =>
      teamMembers.map((member) => ({
        id: member.id,
        label: member.full_name?.trim() || member.email,
      })),
    [teamMembers],
  );

  function toggleTaskSelected(taskId: string) {
    setSelectedIds((current) => ({
      ...current,
      [taskId]: !current[taskId],
    }));
  }

  async function handleQuickComplete(taskId: string) {
    try {
      await completeTask(taskId);
      setRefreshToken((current) => current + 1);
    } catch (quickError) {
      setError(toMessage(quickError, "Unable to complete task."));
    }
  }

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setCreateError("Title is required.");
      return;
    }

    setIsSavingCreate(true);
    setCreateError(null);

    try {
      await createTask({
        title: createForm.title.trim(),
        description: createForm.description.trim() || null,
        due_at: toIsoOrNull(createForm.dueAtLocal),
        priority: createForm.priority,
        assigned_to_user_id: taskPermissions.canAssign
          ? createForm.assignedToUserId || null
          : currentUser?.id,
      });
      setIsCreateOpen(false);
      setCreateForm(DEFAULT_CREATE_FORM);
      setRefreshToken((current) => current + 1);
    } catch (saveError) {
      setCreateError(toMessage(saveError, "Unable to create task."));
    } finally {
      setIsSavingCreate(false);
    }
  }

  async function handleSaveTaskDetail() {
    if (!selectedTask || !detailDraft) {
      return;
    }

    try {
      await updateTask(selectedTask.id, {
        title: detailDraft.title.trim(),
        description: detailDraft.description.trim() || null,
        due_at: toIsoOrNull(detailDraft.dueAtLocal),
        priority: detailDraft.priority,
        status: detailStatus,
        assigned_to_user_id: taskPermissions.canAssign
          ? detailDraft.assignedToUserId || null
          : selectedTask.assigned_to_user_id,
      });
      setRefreshToken((current) => current + 1);
    } catch (saveError) {
      setError(toMessage(saveError, "Unable to save task updates."));
    }
  }

  async function handleToggleCompletion() {
    if (!selectedTask) {
      return;
    }
    try {
      if (selectedTask.status === "done") {
        await reopenTask(selectedTask.id);
      } else {
        await completeTask(selectedTask.id);
      }
      setRefreshToken((current) => current + 1);
    } catch (toggleError) {
      setError(toMessage(toggleError, "Unable to update completion state."));
    }
  }

  async function handleApplyBulk() {
    const taskIds = Object.entries(selectedIds)
      .filter(([, checked]) => checked)
      .map(([taskId]) => taskId);

    if (taskIds.length === 0) {
      setBulkError("Select at least one task.");
      return;
    }

    setIsApplyingBulk(true);
    setBulkError(null);

    try {
      if (bulkAction === "assign") {
        if (!bulkAssignee) {
          setBulkError("Select an assignee.");
          setIsApplyingBulk(false);
          return;
        }
        await bulkTaskUpdate({
          task_ids: taskIds,
          action: "assign",
          assigned_to_user_id: bulkAssignee,
        });
      } else if (bulkAction === "due_date") {
        const dueIso = toIsoOrNull(bulkDueLocal);
        if (!dueIso) {
          setBulkError("Choose a due date.");
          setIsApplyingBulk(false);
          return;
        }
        await bulkTaskUpdate({
          task_ids: taskIds,
          action: "due_date",
          due_at: dueIso,
        });
      } else {
        await bulkTaskUpdate({
          task_ids: taskIds,
          action: "complete",
        });
      }

      setSelectedIds({});
      setRefreshToken((current) => current + 1);
    } catch (applyError) {
      setBulkError(toMessage(applyError, "Unable to apply bulk update."));
    } finally {
      setIsApplyingBulk(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Work</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Tasks</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Manage assignments, due dates, and completion across your workload.
        </p>
      </div>

      <Card className="bg-white shadow-sm">
        <CardHeader className="gap-3 pb-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-xl text-slate-900">Task views</CardTitle>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" className="h-9 rounded-lg" asChild>
                <Link href="/tasks/matrix">Task Matrix</Link>
              </Button>
              <Button
                type="button"
                className="h-9 rounded-lg"
                data-testid="tasks-open-create"
                onClick={() => setIsCreateOpen(true)}
              >
                New Task
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {(Object.keys(VIEW_LABELS) as ViewPreset[]).map((viewKey) => (
              <Button
                key={viewKey}
                type="button"
                variant={activeView === viewKey ? "default" : "outline"}
                className="h-8 rounded-lg"
                disabled={!canUseView(viewKey, taskPermissions.canReadTeam)}
                onClick={() => setActiveView(viewKey)}
              >
                {VIEW_LABELS[viewKey]}
              </Button>
            ))}

            {taskPermissions.canReadAll ? (
              <label className="ml-1 inline-flex items-center gap-2 text-xs text-slate-500">
                <input
                  type="checkbox"
                  checked={showAllTasks}
                  onChange={(event) => setShowAllTasks(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Show all staff tasks
              </label>
            ) : null}
          </div>

          <div className="grid gap-2 sm:grid-cols-[1.3fr_auto] lg:grid-cols-[1.6fr_auto_auto]">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title or description"
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              <option value="active">Open + In progress</option>
              <option value="all">All statuses</option>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="done">Done</option>
              <option value="canceled">Canceled</option>
            </select>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Scope: <span className="font-semibold text-slate-700">{effectiveScope}</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-0">
          {error ? <p className="text-sm text-rose-700">{error}</p> : null}

          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Bulk actions</span>
            <select
              value={bulkAction}
              onChange={(event) => setBulkAction(event.target.value as BulkAction)}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
            >
              <option value="complete">Mark complete</option>
              <option value="assign" disabled={!taskPermissions.canAssign}>
                Assign to user
              </option>
              <option value="due_date">Change due date</option>
            </select>

            {bulkAction === "assign" ? (
              <select
                value={bulkAssignee}
                onChange={(event) => setBulkAssignee(event.target.value)}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
              >
                <option value="">Select assignee</option>
                {assigneeOptions.map((assignee) => (
                  <option key={assignee.id} value={assignee.id}>
                    {assignee.label}
                  </option>
                ))}
              </select>
            ) : null}

            {bulkAction === "due_date" ? (
              <input
                type="datetime-local"
                value={bulkDueLocal}
                onChange={(event) => setBulkDueLocal(event.target.value)}
                className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
              />
            ) : null}

            <Button type="button" className="h-8 rounded-lg px-3" onClick={handleApplyBulk} disabled={isApplyingBulk}>
              {isApplyingBulk ? "Applying..." : `Apply (${selectedTaskCount})`}
            </Button>
            {bulkError ? <span className="text-xs text-rose-700">{bulkError}</span> : null}
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
            <div className="space-y-2" data-testid="tasks-list">
              {isLoading ? <p className="text-sm text-slate-500">Loading tasks...</p> : null}
              {!isLoading && tasks.length === 0 ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                  No tasks found for this view.
                  <div className="mt-2">
                    <Button
                      type="button"
                      className="h-8 rounded-lg"
                      data-testid="tasks-open-create-empty"
                      onClick={() => setIsCreateOpen(true)}
                    >
                      Add your first task
                    </Button>
                  </div>
                </div>
              ) : null}

              {!isLoading
                ? tasks.map((task) => (
                    <div
                      key={task.id}
                      data-testid={`tasks-row-${task.id}`}
                      className={`rounded-lg border px-3 py-3 transition-colors ${
                        selectedTaskId === task.id
                          ? "border-sky-300 bg-sky-50"
                          : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex flex-wrap items-start gap-3">
                        <input
                          type="checkbox"
                          checked={Boolean(selectedIds[task.id])}
                          onChange={() => toggleTaskSelected(task.id)}
                          className="mt-1 h-4 w-4 rounded border-slate-300"
                          aria-label={`Select task ${task.title}`}
                        />
                        <button
                          type="button"
                          className="min-w-[200px] flex-1 text-left"
                          onClick={() => setSelectedTaskId(task.id)}
                        >
                          <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                            <span>Due: {formatDueAt(task.due_at)}</span>
                            <span>Assignee: {task.assigned_to_user_name || "Unassigned"}</span>
                            <span>Priority: {formatPriority(task.priority)}</span>
                          </div>
                        </button>
                        <div className="flex items-center gap-2">
                          <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${statusBadgeClass(task)}`}>
                            {formatStatus(task.status)}
                          </span>
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 rounded-lg"
                            onClick={() => handleQuickComplete(task.id)}
                            disabled={task.status === "done"}
                          >
                            Complete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))
                : null}
            </div>

            <Card className="bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl text-slate-900">Task detail</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                {!selectedTask || !detailDraft ? (
                  <p className="text-sm text-slate-500">Select a task to view and edit details.</p>
                ) : (
                  <>
                    <div>
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-title">
                        Title
                      </label>
                      <input
                        id="task-detail-title"
                        type="text"
                        value={detailDraft.title}
                        onChange={(event) => setDetailDraft((current) => (current ? { ...current, title: event.target.value } : current))}
                        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-description">
                        Description
                      </label>
                      <textarea
                        id="task-detail-description"
                        value={detailDraft.description}
                        onChange={(event) =>
                          setDetailDraft((current) =>
                            current ? { ...current, description: event.target.value } : current,
                          )
                        }
                        className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                      />
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-status">
                          Status
                        </label>
                        <select
                          id="task-detail-status"
                          value={detailStatus}
                          onChange={(event) => setDetailStatus(event.target.value as TaskStatus)}
                          className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                        >
                          <option value="open">Open</option>
                          <option value="in_progress">In Progress</option>
                          <option value="done">Done</option>
                          <option value="canceled">Canceled</option>
                        </select>
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-priority">
                          Priority
                        </label>
                        <select
                          id="task-detail-priority"
                          value={detailDraft.priority}
                          onChange={(event) =>
                            setDetailDraft((current) =>
                              current
                                ? { ...current, priority: event.target.value as TaskPriority }
                                : current,
                            )
                          }
                          className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                        >
                          <option value="low">Low</option>
                          <option value="normal">Normal</option>
                          <option value="high">High</option>
                          <option value="urgent">Urgent</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-due">
                        Due at
                      </label>
                      <input
                        id="task-detail-due"
                        type="datetime-local"
                        value={detailDraft.dueAtLocal}
                        onChange={(event) =>
                          setDetailDraft((current) =>
                            current ? { ...current, dueAtLocal: event.target.value } : current,
                          )
                        }
                        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="task-detail-assignee">
                        Assignee
                      </label>
                      <select
                        id="task-detail-assignee"
                        value={detailDraft.assignedToUserId}
                        onChange={(event) =>
                          setDetailDraft((current) =>
                            current ? { ...current, assignedToUserId: event.target.value } : current,
                          )
                        }
                        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                        disabled={!taskPermissions.canAssign}
                      >
                        <option value="">Unassigned</option>
                        {assigneeOptions.map((assignee) => (
                          <option key={assignee.id} value={assignee.id}>
                            {assignee.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                      <Button type="button" variant="outline" className="h-9 rounded-lg" onClick={handleToggleCompletion}>
                        {selectedTask.status === "done" ? "Reopen" : "Complete"}
                      </Button>
                      <Button type="button" className="h-9 rounded-lg" onClick={handleSaveTaskDetail}>
                        Save Changes
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      {isCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 px-4">
          <Card className="w-full max-w-lg bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">New Task</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <form className="space-y-3" onSubmit={handleCreateTask}>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="tasks-create-title">
                    Title
                  </label>
                  <input
                    id="tasks-create-title"
                    type="text"
                    data-testid="tasks-create-title"
                    className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                    value={createForm.title}
                    onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
                    required
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="tasks-create-description">
                    Description
                  </label>
                  <textarea
                    id="tasks-create-description"
                    className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                    value={createForm.description}
                    onChange={(event) =>
                      setCreateForm((current) => ({ ...current, description: event.target.value }))
                    }
                  />
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="tasks-create-due">
                      Due at
                    </label>
                    <input
                      id="tasks-create-due"
                      type="datetime-local"
                      className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      value={createForm.dueAtLocal}
                      onChange={(event) => setCreateForm((current) => ({ ...current, dueAtLocal: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="tasks-create-priority">
                      Priority
                    </label>
                    <select
                      id="tasks-create-priority"
                      className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      value={createForm.priority}
                      onChange={(event) =>
                        setCreateForm((current) => ({
                          ...current,
                          priority: event.target.value as TaskPriority,
                        }))
                      }
                    >
                      <option value="low">Low</option>
                      <option value="normal">Normal</option>
                      <option value="high">High</option>
                      <option value="urgent">Urgent</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="tasks-create-assignee">
                    Assignee
                  </label>
                  <select
                    id="tasks-create-assignee"
                    className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                    value={createForm.assignedToUserId}
                    onChange={(event) =>
                      setCreateForm((current) => ({ ...current, assignedToUserId: event.target.value }))
                    }
                    disabled={!taskPermissions.canAssign}
                  >
                    <option value="">{taskPermissions.canAssign ? "Unassigned" : "Assigned to me"}</option>
                    {assigneeOptions.map((assignee) => (
                      <option key={assignee.id} value={assignee.id}>
                        {assignee.label}
                      </option>
                    ))}
                  </select>
                </div>

                {createError ? <p className="text-sm text-rose-700">{createError}</p> : null}

                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-9 rounded-lg"
                    onClick={() => {
                      setIsCreateOpen(false);
                      setCreateForm(DEFAULT_CREATE_FORM);
                      setCreateError(null);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" className="h-9 rounded-lg" data-testid="tasks-create-submit" disabled={isSavingCreate}>
                    {isSavingCreate ? "Creating..." : "Create Task"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

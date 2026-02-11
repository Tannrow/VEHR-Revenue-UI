"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import {
  TEAM_LABELS,
  completeTask,
  createTask,
  listTasks,
  loadTaskCalendar,
  taskDueBucket,
  taskPermissionsForRole,
  taskScopeOptionsForRole,
  type TaskPriority,
  type TaskRecord,
  type TaskScope,
} from "@/lib/tasks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MetricCard from "../_components/MetricCard";

type ClientRecord = {
  id: string;
};

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

type TaskCreateFormState = {
  title: string;
  description: string;
  dueAtLocal: string;
  priority: TaskPriority;
};

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const REFERRALS_PLACEHOLDER_COUNT = 14;

const DEFAULT_CREATE_FORM: TaskCreateFormState = {
  title: "",
  description: "",
  dueAtLocal: "",
  priority: "normal",
};

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function toDayKey(value: Date): string {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfWeek(value: Date): Date {
  const copy = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  copy.setDate(copy.getDate() - copy.getDay());
  return copy;
}

function addDays(value: Date, amount: number): Date {
  const copy = new Date(value);
  copy.setDate(copy.getDate() + amount);
  return copy;
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

function formatStatusLabel(status: TaskRecord["status"]): string {
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

function duePillClass(task: TaskRecord): string {
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

function priorityLabel(priority: TaskPriority): string {
  if (priority === "urgent") return "Urgent";
  if (priority === "high") return "High";
  if (priority === "low") return "Low";
  return "Normal";
}

export default function DashboardPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [activeClients, setActiveClients] = useState<number>(0);
  const [scope, setScope] = useState<TaskScope>("self");
  const [teamFilter, setTeamFilter] = useState<string>("");
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [calendarDays, setCalendarDays] = useState<Record<string, { count: number; items: { id: string; title: string; due_at: string }[] }>>({});
  const [monthCursor, setMonthCursor] = useState<Date>(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDayKey, setSelectedDayKey] = useState<string>(() => toDayKey(new Date()));
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isSavingTask, setIsSavingTask] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<TaskCreateFormState>(DEFAULT_CREATE_FORM);

  const [showOutlookComingSoon, setShowOutlookComingSoon] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function loadContext() {
      try {
        const [me, clients] = await Promise.all([
          apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
          apiFetch<ClientRecord[]>("/api/v1/patients", { cache: "no-store" }),
        ]);
        if (!isMounted) {
          return;
        }
        setCurrentUser(me);
        setActiveClients(clients.length);
      } catch {
        if (!isMounted) {
          return;
        }
        setActiveClients(0);
      }
    }

    void loadContext();
    return () => {
      isMounted = false;
    };
  }, []);

  const taskPermissions = useMemo(
    () => taskPermissionsForRole(currentUser?.role),
    [currentUser?.role],
  );

  const scopeOptions = useMemo(
    () => taskScopeOptionsForRole(currentUser?.role),
    [currentUser?.role],
  );

  useEffect(() => {
    if (!scopeOptions.includes(scope)) {
      setScope(scopeOptions[0] ?? "self");
    }
  }, [scope, scopeOptions]);

  const monthGrid = useMemo(() => {
    const monthStart = new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1);
    const gridStart = startOfWeek(monthStart);
    return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
  }, [monthCursor]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    let isMounted = true;

    async function loadTasksAndCalendar() {
      setIsLoadingTasks(true);
      setTaskError(null);

      const monthStart = monthGrid[0];
      const monthEndExclusive = addDays(monthGrid[monthGrid.length - 1], 1);

      try {
        const [taskList, calendar] = await Promise.all([
          listTasks({
            scope,
            team_id: scope !== "self" && teamFilter ? teamFilter : undefined,
            status: ["open", "in_progress"],
            limit: 100,
          }),
          loadTaskCalendar({
            scope,
            start: monthStart.toISOString(),
            end: monthEndExclusive.toISOString(),
          }),
        ]);

        if (!isMounted) {
          return;
        }

        setTasks(taskList.items);
        const nextCalendarDays: Record<string, { count: number; items: { id: string; title: string; due_at: string }[] }> = {};
        for (const day of calendar.days) {
          nextCalendarDays[day.day] = {
            count: day.count,
            items: day.items.map((item) => ({ id: item.id, title: item.title, due_at: item.due_at })),
          };
        }
        setCalendarDays(nextCalendarDays);
      } catch (error) {
        if (!isMounted) {
          return;
        }
        if (error instanceof ApiError && error.status === 403 && scope !== "self") {
          setScope("self");
          setTaskError("This account can only view personal tasks.");
          return;
        }
        setTaskError(toMessage(error, "Unable to load tasks."));
      } finally {
        if (isMounted) {
          setIsLoadingTasks(false);
        }
      }
    }

    void loadTasksAndCalendar();
    return () => {
      isMounted = false;
    };
  }, [currentUser, monthGrid, refreshToken, scope, teamFilter]);

  const filteredTasks = useMemo(() => {
    const selected = selectedDayKey;
    return tasks.filter((task) => {
      if (!task.due_at) {
        return false;
      }
      const date = new Date(task.due_at);
      if (Number.isNaN(date.getTime())) {
        return false;
      }
      return toDayKey(date) === selected;
    });
  }, [selectedDayKey, tasks]);

  const selectedDayAgenda = useMemo(() => {
    return calendarDays[selectedDayKey]?.items ?? [];
  }, [calendarDays, selectedDayKey]);

  const tasksDueToday = useMemo(() => {
    return tasks.filter((task) => taskDueBucket(task.due_at) === "today").length;
  }, [tasks]);

  const overdueItems = useMemo(() => {
    return tasks.filter((task) => taskDueBucket(task.due_at) === "overdue").length;
  }, [tasks]);

  const recentActivity = useMemo(() => {
    const latest = [...tasks]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 5);
    return latest.map((task) => ({
      id: task.id,
      text: `${task.title} · ${formatStatusLabel(task.status)}`,
      time: new Date(task.updated_at).toLocaleString(),
    }));
  }, [tasks]);

  async function handleQuickComplete(taskId: string) {
    try {
      await completeTask(taskId);
      setRefreshToken((current) => current + 1);
    } catch (error) {
      setTaskError(toMessage(error, "Unable to complete task."));
    }
  }

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setCreateError("Title is required.");
      return;
    }

    setIsSavingTask(true);
    setCreateError(null);
    try {
      await createTask({
        title: createForm.title.trim(),
        description: createForm.description.trim() || null,
        due_at: toIsoOrNull(createForm.dueAtLocal),
        priority: createForm.priority,
      });
      setCreateForm(DEFAULT_CREATE_FORM);
      setIsCreateOpen(false);
      setRefreshToken((current) => current + 1);
    } catch (error) {
      setCreateError(toMessage(error, "Unable to create task."));
    } finally {
      setIsSavingTask(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Work</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Operations</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">Focus on the highest-impact work for today.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Tasks due today" value={`${tasksDueToday}`} hint="Needs action" />
        <MetricCard label="Overdue items" value={`${overdueItems}`} hint="Escalate first" />
        <MetricCard label="Active clients" value={`${activeClients}`} hint="Current relationships" />
        <MetricCard label="Open referrals" value={`${REFERRALS_PLACEHOLDER_COUNT}`} hint="Pipeline in progress" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.8fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="gap-3 pb-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="text-xl text-slate-900">Task list</CardTitle>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" className="h-9 rounded-lg" asChild>
                  <Link href="/tasks">View all tasks</Link>
                </Button>
                <Button type="button" className="h-9 rounded-lg px-4" onClick={() => setIsCreateOpen(true)}>
                  Add Task
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {scopeOptions.map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={scope === option ? "default" : "outline"}
                  className="h-8 rounded-lg"
                  onClick={() => setScope(option)}
                >
                  {option === "self" ? "My Tasks" : option === "team" ? "Team" : "All"}
                </Button>
              ))}

              {scope !== "self" ? (
                <select
                  className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
                  value={teamFilter}
                  onChange={(event) => setTeamFilter(event.target.value)}
                >
                  <option value="">All teams</option>
                  {Object.entries(TEAM_LABELS).map(([teamKey, label]) => (
                    <option key={teamKey} value={teamKey}>
                      {label}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>

            {taskPermissions.canReadAll ? (
              <label
                className="inline-flex items-center gap-2 text-xs text-slate-500"
                title="Read-only Outlook calendar overlay will be available in a future release."
              >
                <input
                  type="checkbox"
                  checked={showOutlookComingSoon}
                  onChange={(event) => setShowOutlookComingSoon(event.target.checked)}
                  disabled
                  className="h-4 w-4 rounded border-slate-300"
                />
                Outlook overlay (coming soon)
              </label>
            ) : null}
          </CardHeader>

          <CardContent className="space-y-2 pt-0">
            {taskError ? <p className="text-sm text-rose-700">{taskError}</p> : null}
            {isLoadingTasks ? <p className="text-sm text-slate-500">Loading tasks...</p> : null}

            {!isLoadingTasks && filteredTasks.length === 0 ? (
              <div className="rounded-lg bg-slate-50 px-4 py-5 text-sm text-slate-600">
                No tasks due on {selectedDayKey}. Use Add Task to create one.
              </div>
            ) : null}

            {!isLoadingTasks
              ? filteredTasks.map((task) => (
                  <div key={task.id} className="rounded-lg bg-slate-50 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                      <div className="flex items-center gap-2">
                        <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${duePillClass(task)}`}>
                          {formatStatusLabel(task.status)}
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          className="h-8 rounded-lg"
                          onClick={() => handleQuickComplete(task.id)}
                        >
                          Complete
                        </Button>
                      </div>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                      <span>Due: {formatDueAt(task.due_at)}</span>
                      {scope !== "self" ? (
                        <span>Assignee: {task.assigned_to_user_name || "Unassigned"}</span>
                      ) : null}
                      <span>Priority: {priorityLabel(task.priority)}</span>
                    </div>
                  </div>
                ))
              : null}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-5">
          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-xl text-slate-900">Calendar</CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 rounded-lg px-2"
                    onClick={() =>
                      setMonthCursor(
                        new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1),
                      )
                    }
                  >
                    Prev
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 rounded-lg px-2"
                    onClick={() =>
                      setMonthCursor(
                        new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1),
                      )
                    }
                  >
                    Next
                  </Button>
                </div>
              </div>
              <p className="text-sm text-slate-500">
                {monthCursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </p>
            </CardHeader>
            <CardContent className="space-y-3 pt-0">
              <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                {WEEKDAY_LABELS.map((label) => (
                  <span key={label}>{label}</span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {monthGrid.map((day) => {
                  const dayKey = toDayKey(day);
                  const isSelected = dayKey === selectedDayKey;
                  const isCurrentMonth = day.getMonth() === monthCursor.getMonth();
                  const dayCount = calendarDays[dayKey]?.count ?? 0;
                  return (
                    <button
                      key={dayKey}
                      type="button"
                      onClick={() => setSelectedDayKey(dayKey)}
                      className={`rounded-md border px-1.5 py-2 text-left text-xs transition-colors ${
                        isSelected
                          ? "border-sky-300 bg-sky-50 text-slate-900"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      } ${!isCurrentMonth ? "opacity-60" : "opacity-100"}`}
                    >
                      <span className="block font-semibold">{day.getDate()}</span>
                      <span className="mt-1 block text-[11px] text-slate-500">{dayCount > 0 ? `${dayCount} due` : ""}</span>
                    </button>
                  );
                })}
              </div>

              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Agenda</p>
                <div className="mt-2 space-y-1.5">
                  {selectedDayAgenda.length === 0 ? (
                    <p className="text-xs text-slate-500">No due tasks on this day.</p>
                  ) : (
                    selectedDayAgenda.map((item) => (
                      <div key={item.id} className="rounded-md bg-white px-2 py-1.5 text-xs text-slate-700">
                        <p className="font-semibold text-slate-800">{item.title}</p>
                        <p className="text-slate-500">{formatDueAt(item.due_at)}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">Recent activity</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {recentActivity.length === 0 ? (
                <p className="text-sm text-slate-500">No recent activity yet.</p>
              ) : (
                recentActivity.map((item) => (
                  <div key={item.id} className="rounded-lg bg-slate-50 px-3 py-2">
                    <p className="text-sm text-slate-700">{item.text}</p>
                    <p className="mt-1 text-xs text-slate-500">{item.time}</p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {isCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 px-4">
          <Card className="w-full max-w-lg bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xl text-slate-900">Create Task</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <form className="space-y-3" onSubmit={handleCreateTask}>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="operations-task-title">
                    Title
                  </label>
                  <input
                    id="operations-task-title"
                    type="text"
                    className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                    value={createForm.title}
                    onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
                    required
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="operations-task-description">
                    Description
                  </label>
                  <textarea
                    id="operations-task-description"
                    className="min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                    value={createForm.description}
                    onChange={(event) => setCreateForm((current) => ({ ...current, description: event.target.value }))}
                  />
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="operations-task-due">
                      Due at
                    </label>
                    <input
                      id="operations-task-due"
                      type="datetime-local"
                      className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      value={createForm.dueAtLocal}
                      onChange={(event) => setCreateForm((current) => ({ ...current, dueAtLocal: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor="operations-task-priority">
                      Priority
                    </label>
                    <select
                      id="operations-task-priority"
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

                {createError ? <p className="text-sm text-rose-700">{createError}</p> : null}

                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-9 rounded-lg"
                    onClick={() => {
                      setIsCreateOpen(false);
                      setCreateError(null);
                      setCreateForm(DEFAULT_CREATE_FORM);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" className="h-9 rounded-lg" disabled={isSavingTask}>
                    {isSavingTask ? "Saving..." : "Create Task"}
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


"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { DataListRow } from "@/components/enterprise/data-list-row";
import { PageShell } from "@/components/enterprise/page-shell";
import { SectionCard } from "@/components/enterprise/section-card";
import { SidebarNav, type SidebarNavGroup } from "@/components/enterprise/sidebar-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

function taskStatusTone(task: TaskRecord): "critical" | "attention" | "stable" | "informational" {
  if (task.status === "done") {
    return "stable";
  }
  if (task.status === "canceled") {
    return "informational";
  }
  const bucket = taskDueBucket(task.due_at);
  if (bucket === "overdue") {
    return "critical";
  }
  if (bucket === "today") {
    return "attention";
  }
  return "informational";
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

  const sidebarGroups = useMemo<SidebarNavGroup[]>(() => {
    const scopeItems = scopeOptions.map((option) => ({
      id: option,
      label: option === "self" ? "My Tasks" : option === "team" ? "Team Tasks" : "All Tasks",
      description:
        option === "self"
          ? "Only items assigned to you."
          : option === "team"
            ? "Shared team workload."
            : "Organization-wide queue.",
      active: scope === option,
      onSelect: () => setScope(option),
      testId: `operations-scope-${option}`,
    }));

    return [
      {
        id: "scope",
        label: "Task Scope",
        items: scopeItems,
      },
      {
        id: "workflow",
        label: "Workflow",
        items: [
          {
            id: "tasks-index",
            label: "Open Task Queue",
            description: "Review and triage all active work.",
            badge: tasksDueToday > 0 ? `${tasksDueToday} due today` : undefined,
            href: "/tasks",
            testId: "operations-open-task-queue",
          },
        ],
      },
    ];
  }, [scope, scopeOptions, tasksDueToday]);

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
    <PageShell
      eyebrow="Work"
      title="Operations"
      description="Focus on the highest-impact work for today."
      actions={
        <>
          <Button type="button" variant="outline" asChild>
            <Link href="/tasks">View all tasks</Link>
          </Button>
          <Button type="button" onClick={() => setIsCreateOpen(true)}>
            Add Task
          </Button>
        </>
      }
      metrics={
        <div className="grid gap-[var(--space-16)] md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Tasks due today" value={`${tasksDueToday}`} hint="Needs action" />
          <MetricCard label="Overdue items" value={`${overdueItems}`} hint="Escalate first" />
          <MetricCard label="Active clients" value={`${activeClients}`} hint="Current relationships" />
          <MetricCard label="Open referrals" value={`${REFERRALS_PLACEHOLDER_COUNT}`} hint="Pipeline in progress" />
        </div>
      }
      sidebar={
        <div className="space-y-[var(--space-16)]">
          <SidebarNav groups={sidebarGroups} testId="operations-sidebar-nav" />
          {scope !== "self" ? (
            <SectionCard title="Team Filter" description="Limit the queue to a specific discipline.">
              <label htmlFor="operations-team-filter" className="ui-type-meta font-semibold uppercase tracking-[0.12em]">
                Team
              </label>
              <select
                id="operations-team-filter"
                className="mt-[var(--space-8)] h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] text-[length:var(--font-size-12)] text-[var(--neutral-text)]"
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
            </SectionCard>
          ) : null}
          {taskPermissions.canReadAll ? (
            <SectionCard title="Calendar Overlay" description="Outlook availability will be introduced in a future release.">
              <label
                className="inline-flex items-center gap-[var(--space-8)] ui-type-body text-[var(--neutral-muted)]"
                title="Read-only Outlook calendar overlay will be available in a future release."
              >
                <input
                  type="checkbox"
                  checked={showOutlookComingSoon}
                  onChange={(event) => setShowOutlookComingSoon(event.target.checked)}
                  disabled
                  className="h-[var(--space-16)] w-[var(--space-16)] rounded-[var(--radius-4)] border-[var(--neutral-border)]"
                />
                Outlook overlay (coming soon)
              </label>
            </SectionCard>
          ) : null}
        </div>
      }
    >
      <div className="grid gap-[var(--space-16)] xl:grid-cols-[1.6fr_1fr]">
        <SectionCard
          title={`Task List - ${selectedDayKey}`}
          description="Use scope controls to focus your personal, team, or global queue."
          actions={
            <div className="flex flex-wrap items-center gap-[var(--space-8)]">
              {scopeOptions.map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={scope === option ? "default" : "outline"}
                  size="sm"
                  onClick={() => setScope(option)}
                >
                  {option === "self" ? "My Tasks" : option === "team" ? "Team" : "All"}
                </Button>
              ))}
            </div>
          }
        >
          <div className="space-y-[var(--space-8)]">
            {taskError ? (
              <div className="ui-panel bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-12)] py-[var(--space-8)] text-[var(--status-critical)]">
                {taskError}
              </div>
            ) : null}

            {isLoadingTasks ? <p className="ui-type-body text-[var(--neutral-muted)]">Loading tasks...</p> : null}

            {!isLoadingTasks && filteredTasks.length === 0 ? (
              <div className="ui-panel bg-[var(--muted)] px-[var(--space-16)] py-[var(--space-16)] ui-type-body text-[var(--neutral-muted)]">
                No tasks due on {selectedDayKey}. Use Add Task to create one.
              </div>
            ) : null}

            {!isLoadingTasks
              ? filteredTasks.map((task) => (
                  <DataListRow
                    key={task.id}
                    title={task.title}
                    description={task.description || undefined}
                    meta={[
                      `Due: ${formatDueAt(task.due_at)}`,
                      `Priority: ${priorityLabel(task.priority)}`,
                      ...(scope !== "self" ? [`Assignee: ${task.assigned_to_user_name || "Unassigned"}`] : []),
                    ]}
                    statusLabel={formatStatusLabel(task.status)}
                    statusTone={taskStatusTone(task)}
                    actions={
                      <Button type="button" variant="outline" size="sm" onClick={() => handleQuickComplete(task.id)}>
                        Complete
                      </Button>
                    }
                  />
                ))
              : null}
          </div>
        </SectionCard>

        <div className="flex flex-col gap-[var(--space-16)]">
          <SectionCard
            title="Calendar"
            actions={
              <div className="flex items-center gap-[var(--space-8)]">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1))}
                >
                  Prev
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1))}
                >
                  Next
                </Button>
              </div>
            }
          >
            <div className="space-y-[var(--space-12)]">
              <p className="ui-type-body text-[var(--neutral-muted)]">
                {monthCursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </p>
              <div className="grid grid-cols-7 gap-[var(--space-4)] text-center ui-type-meta font-semibold uppercase tracking-[0.14em]">
                {WEEKDAY_LABELS.map((label) => (
                  <span key={label}>{label}</span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-[var(--space-4)]">
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
                      className={`rounded-[var(--radius-4)] border px-[var(--space-8)] py-[var(--space-8)] text-left text-[length:var(--font-size-12)] transition-colors ${
                        isSelected
                          ? "border-[var(--ring)] bg-[color-mix(in_srgb,var(--accent)_80%,white)] text-[var(--neutral-text)]"
                          : "border-[var(--neutral-border)] bg-[var(--neutral-panel)] text-[var(--neutral-text)] hover:bg-[var(--muted)]"
                      } ${!isCurrentMonth ? "opacity-60" : "opacity-100"}`}
                    >
                      <span className="block font-semibold">{day.getDate()}</span>
                      <span className="ui-type-meta mt-[var(--space-4)] block">
                        {dayCount > 0 ? `${dayCount} due` : ""}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="ui-panel bg-[var(--muted)] px-[var(--space-12)] py-[var(--space-12)]">
                <p className="ui-type-meta font-semibold uppercase tracking-[0.14em]">Agenda</p>
                <div className="mt-[var(--space-8)] space-y-[var(--space-8)]">
                  {selectedDayAgenda.length === 0 ? (
                    <p className="ui-type-meta">No due tasks on this day.</p>
                  ) : (
                    selectedDayAgenda.map((item) => (
                      <DataListRow
                        key={item.id}
                        title={item.title}
                        meta={`Due: ${formatDueAt(item.due_at)}`}
                        statusLabel="Due"
                        statusTone="informational"
                        className="bg-[var(--neutral-panel)]"
                      />
                    ))
                  )}
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Recent Activity">
            <div className="space-y-[var(--space-8)]">
              {recentActivity.length === 0 ? (
                <p className="ui-type-body text-[var(--neutral-muted)]">No recent activity yet.</p>
              ) : (
                recentActivity.map((item) => (
                  <DataListRow
                    key={item.id}
                    title={item.text}
                    meta={item.time}
                    statusLabel="Update"
                    statusTone="informational"
                  />
                ))
              )}
            </div>
          </SectionCard>
        </div>
      </div>

      {isCreateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 px-4">
          <Card className="w-full max-w-lg bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="ui-type-section-title text-[var(--neutral-text)]">Create Task</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <form className="space-y-[var(--space-12)]" onSubmit={handleCreateTask}>
                <div>
                  <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-title">
                    Title
                  </label>
                  <input
                    id="operations-task-title"
                    type="text"
                    className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
                    value={createForm.title}
                    onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
                    required
                  />
                </div>

                <div>
                  <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-description">
                    Description
                  </label>
                  <textarea
                    id="operations-task-description"
                    className="min-h-[var(--space-56)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] py-[var(--space-8)] ui-type-body text-[var(--neutral-text)]"
                    value={createForm.description}
                    onChange={(event) => setCreateForm((current) => ({ ...current, description: event.target.value }))}
                  />
                </div>

                <div className="grid gap-[var(--space-12)] sm:grid-cols-2">
                  <div>
                    <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-due">
                      Due at
                    </label>
                    <input
                      id="operations-task-due"
                      type="datetime-local"
                      className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
                      value={createForm.dueAtLocal}
                      onChange={(event) => setCreateForm((current) => ({ ...current, dueAtLocal: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-[var(--space-4)] block ui-type-meta font-semibold uppercase tracking-[0.12em]" htmlFor="operations-task-priority">
                      Priority
                    </label>
                    <select
                      id="operations-task-priority"
                      className="h-[var(--space-32)] w-full rounded-[var(--radius-6)] border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-12)] ui-type-body text-[var(--neutral-text)]"
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

                {createError ? <p className="ui-type-body text-[var(--status-critical)]">{createError}</p> : null}

                <div className="flex justify-end gap-[var(--space-8)] pt-[var(--space-4)]">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setIsCreateOpen(false);
                      setCreateError(null);
                      setCreateForm(DEFAULT_CREATE_FORM);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={isSavingTask}>
                    {isSavingTask ? "Saving..." : "Create Task"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </PageShell>
  );
}


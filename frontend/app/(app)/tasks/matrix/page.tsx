"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import {
  listTasks,
  loadTaskMatrix,
  taskDueBucket,
  taskPermissionsForRole,
  type TaskDueFilter,
  type TaskMatrixBucketKey,
  type TaskMatrixResponse,
  type TaskRecord,
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

type MatrixScope = "team" | "all";
type MatrixGroupBy = "team" | "user";

type SelectedCell = {
  groupKey: string;
  groupLabel: string;
  bucket: TaskMatrixBucketKey;
  count: number;
};

const BUCKET_ORDER: TaskMatrixBucketKey[] = ["overdue", "today", "next7", "later", "no_due"];
const BUCKET_LABELS: Record<TaskMatrixBucketKey, string> = {
  overdue: "Overdue",
  today: "Today",
  next7: "This Week",
  later: "Later",
  no_due: "No Due Date",
};

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function dueFilterForBucket(bucket: TaskMatrixBucketKey): TaskDueFilter | undefined {
  if (bucket === "overdue") return "overdue";
  if (bucket === "today") return "today";
  if (bucket === "later") return "later";
  if (bucket === "no_due") return "none";
  if (bucket === "next7") return "week";
  return undefined;
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

export default function TasksMatrixPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [matrixScope, setMatrixScope] = useState<MatrixScope>("team");
  const [groupBy, setGroupBy] = useState<MatrixGroupBy>("team");
  const [matrix, setMatrix] = useState<TaskMatrixResponse | null>(null);
  const [isLoadingMatrix, setIsLoadingMatrix] = useState(true);
  const [matrixError, setMatrixError] = useState<string | null>(null);

  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);
  const [cellTasks, setCellTasks] = useState<TaskRecord[]>([]);
  const [isLoadingCellTasks, setIsLoadingCellTasks] = useState(false);
  const [cellError, setCellError] = useState<string | null>(null);

  const permissions = useMemo(
    () => taskPermissionsForRole(currentUser?.role),
    [currentUser?.role],
  );

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
    if (permissions.canReadAll) {
      return;
    }
    if (matrixScope === "all") {
      setMatrixScope("team");
    }
  }, [matrixScope, permissions.canReadAll]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    if (!permissions.canReadTeam && !permissions.canReadAll) {
      setIsLoadingMatrix(false);
      setMatrixError("This account does not have access to team-level matrix data.");
      return;
    }

    let isMounted = true;

    async function loadMatrixRows() {
      setIsLoadingMatrix(true);
      setMatrixError(null);
      try {
        const scopeToUse: MatrixScope = matrixScope === "all" && permissions.canReadAll ? "all" : "team";
        const result = await loadTaskMatrix({
          scope: scopeToUse,
          group_by: groupBy,
        });
        if (!isMounted) {
          return;
        }
        setMatrix(result);
      } catch (error) {
        if (!isMounted) {
          return;
        }
        setMatrixError(toMessage(error, "Unable to load task matrix."));
      } finally {
        if (isMounted) {
          setIsLoadingMatrix(false);
        }
      }
    }

    void loadMatrixRows();
    return () => {
      isMounted = false;
    };
  }, [currentUser, groupBy, matrixScope, permissions.canReadAll, permissions.canReadTeam]);

  async function loadTasksForCell(cell: SelectedCell) {
    if (!matrix) {
      return;
    }
    const dueFilter = dueFilterForBucket(cell.bucket);
    const scopeToUse: MatrixScope = matrixScope === "all" && permissions.canReadAll ? "all" : "team";

    setIsLoadingCellTasks(true);
    setCellError(null);
    try {
      const response = await listTasks({
        scope: scopeToUse,
        due: dueFilter,
        status: ["open", "in_progress"],
        assigned_to: groupBy === "user" && cell.groupKey !== "unassigned" ? cell.groupKey : undefined,
        team_id: groupBy === "team" && cell.groupKey !== "unassigned" ? cell.groupKey : undefined,
        limit: 200,
      });

      let rows = response.items;
      if (groupBy === "user" && cell.groupKey === "unassigned") {
        rows = rows.filter((task) => !task.assigned_to_user_id);
      }
      if (groupBy === "team" && cell.groupKey === "unassigned") {
        rows = rows.filter((task) => !task.assigned_team_id);
      }
      rows = rows.filter((task) => taskDueBucket(task.due_at) === cell.bucket);

      setCellTasks(rows);
    } catch (error) {
      setCellError(toMessage(error, "Unable to load tasks for this matrix cell."));
      setCellTasks([]);
    } finally {
      setIsLoadingCellTasks(false);
    }
  }

  async function handleSelectCell(cell: SelectedCell) {
    setSelectedCell(cell);
    await loadTasksForCell(cell);
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Work</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Task Matrix</h1>
        <p className="max-w-2xl text-base leading-7 text-slate-600">
          Compare workload by team or user and drill into priority buckets.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant={groupBy === "team" ? "default" : "outline"} className="h-8 rounded-lg" onClick={() => setGroupBy("team")}>
          Group by Team
        </Button>
        <Button type="button" variant={groupBy === "user" ? "default" : "outline"} className="h-8 rounded-lg" onClick={() => setGroupBy("user")}>
          Group by User
        </Button>
        <div className="mx-1 h-6 w-px bg-slate-200" />
        <Button type="button" variant={matrixScope === "team" ? "default" : "outline"} className="h-8 rounded-lg" onClick={() => setMatrixScope("team")}>
          My Team
        </Button>
        <Button
          type="button"
          variant={matrixScope === "all" ? "default" : "outline"}
          className="h-8 rounded-lg"
          disabled={!permissions.canReadAll}
          onClick={() => setMatrixScope("all")}
        >
          All Staff
        </Button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.8fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Matrix</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {matrixError ? <p className="text-sm text-rose-700">{matrixError}</p> : null}
            {isLoadingMatrix ? <p className="text-sm text-slate-500">Loading matrix...</p> : null}

            {!isLoadingMatrix && !matrixError ? (
              <div className="overflow-auto">
                <table className="min-w-full border-separate border-spacing-y-2 text-sm">
                  <thead>
                    <tr>
                      <th className="px-2 text-left text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {groupBy === "team" ? "Team" : "User"}
                      </th>
                      {BUCKET_ORDER.map((bucket) => (
                        <th key={bucket} className="px-2 text-center text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                          {BUCKET_LABELS[bucket]}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {matrix?.rows.length ? (
                      matrix.rows.map((row) => (
                        <tr key={row.group_key}>
                          <td className="rounded-l-lg border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-800">
                            {row.group_label}
                          </td>
                          {BUCKET_ORDER.map((bucket) => {
                            const count = row.buckets[bucket]?.count ?? 0;
                            const isActive =
                              selectedCell?.groupKey === row.group_key &&
                              selectedCell?.bucket === bucket;
                            return (
                              <td key={`${row.group_key}-${bucket}`} className="border-y border-slate-200 bg-white px-2 py-2 last:rounded-r-lg last:border-r">
                                <button
                                  type="button"
                                  className={`w-full rounded-md px-2 py-2 text-xs font-semibold transition-colors ${
                                    isActive
                                      ? "bg-sky-100 text-sky-900"
                                      : "bg-slate-50 text-slate-700 hover:bg-slate-100"
                                  }`}
                                  onClick={() =>
                                    handleSelectCell({
                                      groupKey: row.group_key,
                                      groupLabel: row.group_label,
                                      bucket,
                                      count,
                                    })
                                  }
                                >
                                  {count}
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={BUCKET_ORDER.length + 1} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-5 text-center text-slate-600">
                          No matrix data available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl text-slate-900">Cell detail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {!selectedCell ? (
              <p className="text-sm text-slate-500">Select a matrix cell to inspect matching tasks.</p>
            ) : (
              <>
                <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  <p className="font-semibold">{selectedCell.groupLabel}</p>
                  <p className="text-xs text-slate-500">{BUCKET_LABELS[selectedCell.bucket]}</p>
                </div>

                {cellError ? <p className="text-sm text-rose-700">{cellError}</p> : null}
                {isLoadingCellTasks ? <p className="text-sm text-slate-500">Loading tasks...</p> : null}

                {!isLoadingCellTasks && !cellError && cellTasks.length === 0 ? (
                  <p className="text-sm text-slate-500">No tasks in this cell.</p>
                ) : null}

                {!isLoadingCellTasks && !cellError
                  ? cellTasks.map((task) => (
                      <div key={task.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          Due: {formatDueAt(task.due_at)} · Assignee: {task.assigned_to_user_name || "Unassigned"}
                        </p>
                      </div>
                    ))
                  : null}

                <Button type="button" variant="outline" className="h-8 rounded-lg w-full" asChild>
                  <Link href="/tasks">Open full tasks list</Link>
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

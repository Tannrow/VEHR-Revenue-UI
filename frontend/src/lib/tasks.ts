import { apiFetch } from "@/lib/api";

export type TaskStatus = "open" | "in_progress" | "done" | "canceled";
export type TaskPriority = "low" | "normal" | "high" | "urgent";
export type TaskScope = "self" | "team" | "all";
export type TaskDueFilter = "today" | "overdue" | "week" | "later" | "none";
export type TaskMatrixBucketKey = "overdue" | "today" | "next7" | "later" | "no_due";

export type TaskRecord = {
  id: string;
  organization_id: string;
  title: string;
  description?: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_at?: string | null;
  completed_at?: string | null;
  created_by_user_id: string;
  assigned_to_user_id?: string | null;
  assigned_to_user_name?: string | null;
  assigned_team_id?: string | null;
  assigned_team_label?: string | null;
  related_type?: string | null;
  related_id?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type TaskListResponse = {
  items: TaskRecord[];
  total: number;
  limit: number;
  offset: number;
  counts: Record<string, number>;
};

export type TaskCreatePayload = {
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  due_at?: string | null;
  assigned_to_user_id?: string | null;
  assigned_team_id?: string | null;
  related_type?: string | null;
  related_id?: string | null;
  tags?: string[];
};

export type TaskUpdatePayload = Partial<TaskCreatePayload> & {
  status?: TaskStatus;
};

export type TaskCalendarItem = {
  id: string;
  title: string;
  due_at: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to_user_id?: string | null;
  assigned_to_user_name?: string | null;
};

export type TaskCalendarDay = {
  day: string;
  count: number;
  items: TaskCalendarItem[];
};

export type TaskCalendarResponse = {
  start: string;
  end: string;
  days: TaskCalendarDay[];
};

export type TaskMatrixBucket = {
  count: number;
  sample_task_ids: string[];
};

export type TaskMatrixRow = {
  group_key: string;
  group_label: string;
  buckets: Record<string, TaskMatrixBucket>;
};

export type TaskMatrixResponse = {
  scope: "team" | "all";
  group_by: "team" | "user";
  rows: TaskMatrixRow[];
};

export type TaskBulkPayload = {
  task_ids: string[];
  action: "complete" | "assign" | "due_date";
  assigned_to_user_id?: string | null;
  assigned_team_id?: string | null;
  due_at?: string | null;
};

function toQuery(params: Record<string, string | number | null | undefined | string[]>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null) continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        query.append(key, item);
      }
      continue;
    }
    query.set(key, String(value));
  }
  const asString = query.toString();
  return asString ? `?${asString}` : "";
}

export async function listTasks(params: {
  scope?: TaskScope;
  status?: TaskStatus[];
  due?: TaskDueFilter;
  assigned_to?: "me" | string;
  team_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<TaskListResponse> {
  const query = toQuery({
    scope: params.scope ?? "self",
    status: params.status,
    due: params.due,
    assigned_to: params.assigned_to,
    team_id: params.team_id,
    search: params.search,
    limit: params.limit ?? 50,
    offset: params.offset ?? 0,
  });
  return apiFetch<TaskListResponse>(`/api/v1/tasks${query}`, { cache: "no-store" });
}

export async function createTask(payload: TaskCreatePayload): Promise<TaskRecord> {
  return apiFetch<TaskRecord>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTask(taskId: string): Promise<TaskRecord> {
  return apiFetch<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, { cache: "no-store" });
}

export async function updateTask(taskId: string, payload: TaskUpdatePayload): Promise<TaskRecord> {
  return apiFetch<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function completeTask(taskId: string): Promise<TaskRecord> {
  return apiFetch<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}/complete`, {
    method: "POST",
  });
}

export async function reopenTask(taskId: string): Promise<TaskRecord> {
  return apiFetch<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}/reopen`, {
    method: "POST",
  });
}

export async function bulkTaskUpdate(payload: TaskBulkPayload): Promise<{ updated_task_ids: string[]; action: string; updated_count: number }> {
  return apiFetch<{ updated_task_ids: string[]; action: string; updated_count: number }>("/api/v1/tasks/bulk", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loadTaskCalendar(params: {
  scope?: TaskScope;
  start?: string;
  end?: string;
} = {}): Promise<TaskCalendarResponse> {
  const query = toQuery({
    scope: params.scope ?? "self",
    start: params.start,
    end: params.end,
  });
  return apiFetch<TaskCalendarResponse>(`/api/v1/tasks/calendar${query}`, { cache: "no-store" });
}

export async function loadTaskMatrix(params: {
  scope?: "team" | "all";
  group_by?: "team" | "user";
} = {}): Promise<TaskMatrixResponse> {
  const query = toQuery({
    scope: params.scope ?? "team",
    group_by: params.group_by ?? "team",
  });
  return apiFetch<TaskMatrixResponse>(`/api/v1/tasks/matrix${query}`, { cache: "no-store" });
}

export type TaskUiPermissions = {
  canReadSelf: boolean;
  canWriteSelf: boolean;
  canReadTeam: boolean;
  canReadAll: boolean;
  canAssign: boolean;
};

const TASK_PERMISSION_BY_ROLE: Record<string, TaskUiPermissions> = {
  admin: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: true, canAssign: true },
  office_manager: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: true, canAssign: true },
  sud_supervisor: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: true, canAssign: true },
  counselor: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: false, canAssign: false },
  case_manager: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: false, canAssign: false },
  receptionist: { canReadSelf: true, canWriteSelf: true, canReadTeam: false, canReadAll: false, canAssign: false },
  billing: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: false, canAssign: false },
  compliance: { canReadSelf: true, canWriteSelf: true, canReadTeam: true, canReadAll: false, canAssign: false },
  fcs_staff: { canReadSelf: true, canWriteSelf: true, canReadTeam: false, canReadAll: false, canAssign: false },
  driver: { canReadSelf: true, canWriteSelf: true, canReadTeam: false, canReadAll: false, canAssign: false },
  intern: { canReadSelf: true, canWriteSelf: false, canReadTeam: false, canReadAll: false, canAssign: false },
};

const DEFAULT_TASK_PERMISSIONS: TaskUiPermissions = {
  canReadSelf: true,
  canWriteSelf: false,
  canReadTeam: false,
  canReadAll: false,
  canAssign: false,
};

export const TEAM_LABELS: Record<string, string> = {
  admissions: "Admissions team",
  clinical: "Clinical team",
  billing: "Billing",
  compliance: "Compliance",
  reception: "Reception",
  workforce: "Workforce",
  unassigned: "Unassigned",
};

export function taskPermissionsForRole(role?: string | null): TaskUiPermissions {
  if (!role) {
    return DEFAULT_TASK_PERMISSIONS;
  }
  return TASK_PERMISSION_BY_ROLE[role] ?? DEFAULT_TASK_PERMISSIONS;
}

export function taskScopeOptionsForRole(role?: string | null): TaskScope[] {
  const permissions = taskPermissionsForRole(role);
  const options: TaskScope[] = ["self"];
  if (permissions.canReadTeam) {
    options.push("team");
  }
  if (permissions.canReadAll) {
    options.push("all");
  }
  return options;
}

export function taskDueBucket(dueAt: string | null | undefined, nowDate: Date = new Date()): TaskMatrixBucketKey {
  if (!dueAt) {
    return "no_due";
  }
  const dueDate = new Date(dueAt);
  if (Number.isNaN(dueDate.getTime())) {
    return "no_due";
  }

  const startToday = new Date(
    nowDate.getFullYear(),
    nowDate.getMonth(),
    nowDate.getDate(),
    0,
    0,
    0,
    0,
  );
  const startTomorrow = new Date(startToday);
  startTomorrow.setDate(startTomorrow.getDate() + 1);
  const startInEightDays = new Date(startToday);
  startInEightDays.setDate(startInEightDays.getDate() + 8);

  if (dueDate < startToday) {
    return "overdue";
  }
  if (dueDate >= startToday && dueDate < startTomorrow) {
    return "today";
  }
  if (dueDate < startInEightDays) {
    return "next7";
  }
  return "later";
}

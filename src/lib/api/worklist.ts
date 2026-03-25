import { z } from "zod";

import { apiClientFetch } from "@/lib/api/client";
import { isFetchFailedMessage } from "@/lib/error-messages";

export const REVENUE_WORKLIST_API_PATH = "/api/revenue/worklist";
export const REVENUE_WORKLIST_ACTIONS_API_PATH = "/api/revenue/worklist/actions";

const worklistRecommendedActionSchema = z.object({
  type: z.string().min(1),
  confidence: z.string().min(1),
  reason: z.string().min(1),
});

const worklistTimelineEntrySchema = z.object({
  at: z.string().min(1),
  event: z.string().min(1),
  detail: z.string().min(1),
});

const worklistAssigneeSchema = z.object({
  user_id: z.string().nullable().optional(),
  user_name: z.string().nullable().optional(),
  team_id: z.string().nullable().optional(),
  team_label: z.string().nullable().optional(),
});

const worklistItemSchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  status: z.string().min(1),
  claim_id: z.string().nullable().optional(),
  claim_ref: z.string().nullable().optional(),
  patient_id: z.string().nullable().optional(),
  patient_name: z.string().nullable().optional(),
  payer: z.string().nullable().optional(),
  facility: z.string().nullable().optional(),
  amount_at_risk: z.string().min(1),
  amount_at_risk_cents: z.number(),
  aging_days: z.number().nullable().optional(),
  aging_bucket: z.string().min(1),
  priority: z.string().min(1),
  sla_state: z.string().min(1),
  escalation_state: z.string().min(1),
  reason_codes: z.array(z.string()),
  recommended_action: worklistRecommendedActionSchema,
  allowed_actions: z.array(z.string()),
  assignee: worklistAssigneeSchema,
  updated_at: z.string().min(1),
  created_at: z.string().min(1),
  timeline_summary: z.array(worklistTimelineEntrySchema),
});

const worklistSummarySchema = z.object({
  total: z.number(),
  priority_counts: z.record(z.string(), z.number()),
});

export const revenueWorklistPageSchema = z.object({
  items: z.array(worklistItemSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_pages: z.number(),
  sort_by: z.string().min(1),
  sort_direction: z.string().min(1),
  summary: worklistSummarySchema,
});

const worklistActionResponseSchema = z.object({
  action: z.string().min(1),
  updated_work_item_ids: z.array(z.string()),
  updated_count: z.number(),
});

export type RevenueWorklistPage = z.infer<typeof revenueWorklistPageSchema>;
export type RevenueWorklistItem = z.infer<typeof worklistItemSchema>;
export type RevenueWorklistActionResponse = z.infer<typeof worklistActionResponseSchema>;

function buildQuery(params?: Record<string, string | number | null | undefined>): string {
  if (!params) {
    return "";
  }

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || typeof value === "undefined" || value === "") {
      return;
    }
    searchParams.set(key, String(value));
  });

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function formatWorklistError(status: number, payload: unknown, text: string): string {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const detail = "detail" in payload ? payload.detail : null;
    const error = "error" in payload ? payload.error : null;
    if (typeof error === "string" && error.trim()) {
      return error.trim();
    }
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
  }

  if (typeof payload === "string" && payload.trim()) {
    return isFetchFailedMessage(payload) ? "Unable to reach the VEHR worklist endpoint right now." : payload.trim();
  }

  if (text.trim()) {
    return text.trim();
  }

  return `Unable to load the worklist (status ${status}).`;
}

export async function fetchRevenueWorklist(params?: Record<string, string | number | null | undefined>): Promise<RevenueWorklistPage> {
  const response = await apiClientFetch(`${REVENUE_WORKLIST_API_PATH}${buildQuery(params)}`);

  if (!response.ok) {
    throw new Error(formatWorklistError(response.status, response.data, response.text));
  }

  return revenueWorklistPageSchema.parse(response.data);
}

export async function runRevenueWorklistAction(payload: {
  workItemIds: string[];
  action: "assign" | "reassign" | "mark_in_progress";
  assignedToUserId?: string | null;
  assignedTeamId?: string | null;
}): Promise<RevenueWorklistActionResponse> {
  const response = await apiClientFetch(REVENUE_WORKLIST_ACTIONS_API_PATH, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      work_item_ids: payload.workItemIds,
      action: payload.action,
      assigned_to_user_id: payload.assignedToUserId ?? null,
      assigned_team_id: payload.assignedTeamId ?? null,
    }),
  });

  if (!response.ok) {
    throw new Error(formatWorklistError(response.status, response.data, response.text));
  }

  return worklistActionResponseSchema.parse(response.data);
}

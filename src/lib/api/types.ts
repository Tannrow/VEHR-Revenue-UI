import { z } from "zod";

import type { components, paths } from "@/lib/api/schema";

export type JsonValue = components["schemas"]["JsonValue"];
export type JsonRecord = { [key: string]: JsonValue };
export type RevenueSnapshotResponse =
  paths["/api/v1/revenue/snapshots/latest"]["get"]["responses"][200]["content"]["application/json"];
export type RevenueSnapshotMissing = components["schemas"]["RevenueSnapshotMissing"];
export type ApiErrorResponse = components["schemas"]["ApiErrorResponse"];

type ExactKeySet<Actual extends string, Expected extends string> = [Exclude<Actual, Expected>, Exclude<Expected, Actual>] extends [
  never,
  never,
]
  ? true
  : never;

const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([z.string(), z.number(), z.boolean(), z.null(), z.array(jsonValueSchema), z.record(z.string(), jsonValueSchema)]),
);

const revenueSnapshotResponseFields = {
  snapshot_id: z.string().min(1),
  generated_at: z.string().min(1),
  total_exposure_cents: z.number(),
  expected_recovery_30_day_cents: z.number(),
  short_term_cash_opportunity_cents: z.number(),
  high_risk_claim_count: z.number(),
  critical_pre_submission_count: z.number(),
  top_aggressive_payers: z.array(jsonValueSchema),
  top_revenue_loss_drivers: z.array(jsonValueSchema),
  top_worklist: z.array(jsonValueSchema),
} satisfies Record<keyof RevenueSnapshotResponse, z.ZodType>;

const _assertExactRevenueSnapshotResponseFields: ExactKeySet<
  keyof typeof revenueSnapshotResponseFields & string,
  keyof RevenueSnapshotResponse & string
> = true;

void _assertExactRevenueSnapshotResponseFields;

export const revenueSnapshotResponseSchema: z.ZodType<RevenueSnapshotResponse> = z
  .object(revenueSnapshotResponseFields)
  .strict();

export const revenueSnapshotMissingSchema: z.ZodType<RevenueSnapshotMissing> = z
  .object({
    error: z.literal("snapshot_not_found"),
    detail: jsonValueSchema.optional(),
    message: z.string().optional(),
  })
  .passthrough();

export const apiErrorResponseSchema: z.ZodType<ApiErrorResponse> = z
  .object({
    error: z.string().min(1),
    detail: jsonValueSchema.optional(),
    message: z.string().optional(),
  })
  .passthrough();

export function assertSnapshotExists(
  snapshot: RevenueSnapshotResponse | null | undefined,
): asserts snapshot is RevenueSnapshotResponse {
  if (!snapshot) {
    throw new Error("Revenue snapshot data is not available.");
  }
}

export function safeSnapshotAccess<Key extends keyof RevenueSnapshotResponse>(
  snapshot: RevenueSnapshotResponse | null | undefined,
  key: Key,
): RevenueSnapshotResponse[Key] | null {
  if (!snapshot) {
    return null;
  }

  return snapshot[key];
}

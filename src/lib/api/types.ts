import { z } from "zod";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonRecord = { [key: string]: JsonValue };

const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([z.string(), z.number(), z.boolean(), z.null(), z.array(jsonValueSchema), z.record(z.string(), jsonValueSchema)]),
);

export const revenueSnapshotResponseSchema = z
  .object({
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
  })
  .strict();

export const revenueSnapshotMissingSchema = z
  .object({
    error: z.literal("snapshot_not_found"),
    detail: z.string().optional(),
    message: z.string().optional(),
  })
  .passthrough();

export const apiErrorResponseSchema = z
  .object({
    error: z.string().min(1),
    detail: z.string().optional(),
    message: z.string().optional(),
  })
  .passthrough();

export type RevenueSnapshotResponse = z.infer<typeof revenueSnapshotResponseSchema>;
export type RevenueSnapshotMissing = z.infer<typeof revenueSnapshotMissingSchema>;
export type ApiErrorResponse = z.infer<typeof apiErrorResponseSchema>;

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

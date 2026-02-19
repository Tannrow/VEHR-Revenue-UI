import { apiFetch } from "@/lib/api";

export type AggressivePayer = {
  payer: string;
  aggression_score: number;
  aggression_tier: string;
  aggression_drivers: string[];
};

export type RevenueCommandSnapshot = {
  id: string;
  generated_at: string;
  org_id: string;
  total_exposure: string;
  expected_recovery_30_day: string;
  short_term_cash_opportunity: string;
  high_risk_claim_count: number;
  critical_pre_submission_count: number;
  top_aggressive_payers: AggressivePayer[];
  top_revenue_loss_drivers: string[];
  worklist_priority_summary: Record<string, number>;
  execution_plan_30_day: Array<Record<string, unknown>>;
  structural_moves_90_day: string[];
  aggression_change_alerts: Array<Record<string, unknown>>;
  scoring_versions: {
    risk_version: string;
    aggression_version: string;
    pre_submission_version: string;
  };
};

export async function fetchLatestRevenueSnapshot(): Promise<RevenueCommandSnapshot> {
  return apiFetch<RevenueCommandSnapshot>("/api/v1/revenue/command/latest", { cache: "no-store" });
}

export async function fetchRevenueSnapshotHistory(limit = 10): Promise<RevenueCommandSnapshot[]> {
  const safeLimit = Math.min(Math.max(limit, 1), 90);
  return apiFetch<RevenueCommandSnapshot[]>(`/api/v1/revenue/command/history?limit=${safeLimit}`, { cache: "no-store" });
}

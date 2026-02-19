export type RevenueSnapshotAggressivePayer = {
  payer: string;
  aggression_score: number;
  aggression_tier: string;
  aggression_drivers: string[];
};

export type RevenueSnapshotWorklistItem = {
  id: string;
  claim_id: string;
  payer: string | null;
  status: string | null;
  aging_days: number;
  dollars_per_hour_cents: number;
  task: string;
  priority: string | null;
};

export type RevenueSnapshot = {
  snapshot_id: string;
  organization_id: string;
  generated_at: string;
  total_exposure_cents: number;
  expected_recovery_30_day_cents: number;
  short_term_cash_opportunity_cents: number;
  high_risk_claim_count: number;
  critical_pre_submission_count: number;
  top_aggressive_payers: RevenueSnapshotAggressivePayer[];
  top_revenue_loss_drivers: string[];
  worklist_priority_summary: Record<string, number>;
  top_worklist: RevenueSnapshotWorklistItem[];
  execution_plan_30_day: Array<Record<string, unknown>>;
  structural_moves_90_day: string[];
  aggression_change_alerts: Array<Record<string, unknown>>;
  scoring_versions: {
    risk_version: string;
    aggression_version: string;
    pre_submission_version: string;
  };
};

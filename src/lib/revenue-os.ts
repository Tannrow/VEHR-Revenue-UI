import type { ClaimRecord } from "@/lib/api/claims";
import type { JsonValue, RevenueSnapshotResponse } from "@/lib/api/types";

export type QueueStatus = "new" | "ready" | "blocked" | "appeal" | "resolved";
export type QueuePriority = "critical" | "high" | "medium" | "low";

export type QueueItem = {
  id: string;
  claimId: string;
  claimRecordId: string;
  sourceClaimId: string;
  patient: string | null;
  payer: string;
  queue: string;
  claimStatus: string;
  status: QueueStatus;
  priority: QueuePriority;
  agingDays: number;
  valuePerHourCents: number;
  createdAt: string | null;
  updatedAt: string | null;
  nextAction: string;
  summary: string;
  evidence: Array<{ label: string; detail: string }>;
  timeline: Array<{ at: string; event: string; actor: string }>;
};

export type InsightMetric = {
  label: string;
  value: string;
  trend: string;
  change: string;
  drillLabel: string;
};

export type PipelineStage = {
  label: string;
  count: number;
  tone: "neutral" | "warning" | "good";
  action: string;
};

export type PolicyRule = {
  id: string;
  name: string;
  condition: string;
  outcome: string;
  coverage: string;
};

type SnapshotWorklistItem = {
  id: string;
  claim_id: string;
  payer?: string | null;
  status?: string | null;
  aging_days: number;
  dollars_per_hour_cents: number;
  task: string;
  priority?: string | null;
};

function isRecord(value: JsonValue): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSnapshotWorklistItem(value: JsonValue): value is SnapshotWorklistItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.claim_id === "string" &&
    typeof value.task === "string" &&
    typeof value.dollars_per_hour_cents === "number"
  );
}

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

function formatTimestampLabel(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.valueOf())) {
    return null;
  }

  return parsed.toLocaleString();
}

function normalizeQueueStatus(status: string | null | undefined): QueueStatus {
  switch ((status ?? "").trim().toUpperCase()) {
    case "DENIED":
      return "blocked";
    case "PARTIAL":
      return "ready";
    case "PAID":
      return "resolved";
    case "OPEN":
    default:
      return "new";
  }
}

function normalizeQueuePriority(priority: string | null | undefined, agingDays: number): QueuePriority {
  const normalizedPriority = (priority ?? "").trim().toLowerCase();

  if (normalizedPriority === "critical") {
    return "critical";
  }

  if (normalizedPriority === "high") {
    return agingDays >= 120 ? "critical" : "high";
  }

  if (normalizedPriority === "medium") {
    return agingDays >= 120 ? "high" : "medium";
  }

  if (normalizedPriority === "low") {
    if (agingDays >= 120) {
      return "critical";
    }

    if (agingDays >= 90) {
      return "high";
    }

    return "low";
  }

  if (agingDays >= 120) {
    return "critical";
  }

  if (agingDays >= 90) {
    return "high";
  }

  if (agingDays >= 45) {
    return "medium";
  }

  return "low";
}

function buildQueueLabel(task: string, status: string | null | undefined): string {
  const normalizedTask = task.toLowerCase();
  const normalizedStatus = (status ?? "").trim().toUpperCase();

  if (normalizedTask.includes("denial") || normalizedStatus === "DENIED") {
    return "Denied claims";
  }

  if (normalizedTask.includes("balance") || normalizedStatus === "OPEN" || normalizedStatus === "PARTIAL") {
    return "Open balances";
  }

  if (normalizedStatus === "PAID") {
    return "Resolved payments";
  }

  return "Revenue follow-up";
}

function buildSummary(input: {
  claimStatus: string;
  agingDays: number;
  payer: string;
  task: string;
}): string {
  const statusLabel = input.claimStatus === "Unknown" ? "This claim is in the live snapshot" : `Live status: ${input.claimStatus}`;
  const agingLabel = input.agingDays > 0 ? `Aging ${input.agingDays} day${input.agingDays === 1 ? "" : "s"}.` : "Freshly surfaced in the current queue.";

  return `${statusLabel}. ${agingLabel} ${input.task} for ${input.payer}.`;
}

function buildTimeline(input: {
  createdAt: string | null;
  updatedAt: string | null;
  snapshotGeneratedAt: string;
}): Array<{ at: string; event: string; actor: string }> {
  const entries: Array<{ at: string; event: string; actor: string }> = [];
  const createdLabel = formatTimestampLabel(input.createdAt);
  const updatedLabel = formatTimestampLabel(input.updatedAt);
  const snapshotLabel = formatTimestampLabel(input.snapshotGeneratedAt) ?? "Current snapshot";

  if (createdLabel) {
    entries.push({
      at: createdLabel,
      event: "Claim record created",
      actor: "Claims service",
    });
  }

  if (updatedLabel && updatedLabel !== createdLabel) {
    entries.push({
      at: updatedLabel,
      event: "Claim record updated",
      actor: "Claims service",
    });
  }

  entries.push({
    at: snapshotLabel,
    event: "Included in the latest revenue snapshot",
    actor: "Revenue command snapshot",
  });

  return entries;
}

function buildClaimLookup(claims: ClaimRecord[]): Map<string, ClaimRecord> {
  const claimLookup = new Map<string, ClaimRecord>();

  for (const claim of claims) {
    if (typeof claim.id === "string" && claim.id.trim()) {
      claimLookup.set(claim.id, claim);
    }

    if (typeof claim.external_claim_id === "string" && claim.external_claim_id.trim()) {
      claimLookup.set(claim.external_claim_id, claim);
    }
  }

  return claimLookup;
}

export function buildRevenueQueueItems(
  snapshot: RevenueSnapshotResponse,
  claims: ClaimRecord[],
): QueueItem[] {
  const claimLookup = buildClaimLookup(claims);

  return snapshot.top_worklist.filter(isSnapshotWorklistItem).map((workItem) => {
    const claim = claimLookup.get(workItem.claim_id);
    const payer = claim?.payer_name?.trim() || workItem.payer?.trim() || "Payer pending";
    const claimStatus = claim?.status?.trim() || workItem.status?.trim() || "Unknown";
    const agingDays = Math.max(workItem.aging_days ?? 0, 0);
    const priority = normalizeQueuePriority(workItem.priority, agingDays);
    const queue = buildQueueLabel(workItem.task, claimStatus);
    const patient = claim?.patient_name?.trim() || null;
    const createdAt = claim?.created_at ?? null;
    const updatedAt = claim?.updated_at ?? null;
    const claimId = claim?.external_claim_id?.trim() || workItem.claim_id;

    return {
      id: workItem.id,
      claimId,
      claimRecordId: claim?.id?.trim() || workItem.claim_id,
      sourceClaimId: workItem.claim_id,
      patient,
      payer,
      queue,
      claimStatus,
      status: normalizeQueueStatus(claimStatus),
      priority,
      agingDays,
      valuePerHourCents: workItem.dollars_per_hour_cents,
      createdAt,
      updatedAt,
      nextAction: workItem.task,
      summary: buildSummary({
        claimStatus,
        agingDays,
        payer,
        task: workItem.task,
      }),
      evidence: [
        { label: "Snapshot task", detail: workItem.task },
        { label: "Live status", detail: claimStatus },
        { label: "Queue", detail: queue },
        {
          label: "Value per hour",
          detail: formatMoney(workItem.dollars_per_hour_cents),
        },
      ],
      timeline: buildTimeline({
        createdAt,
        updatedAt,
        snapshotGeneratedAt: snapshot.generated_at,
      }),
    };
  });
}

export function buildInsightMetrics(
  snapshot: RevenueSnapshotResponse,
  queueItems: QueueItem[],
): InsightMetric[] {
  const blockedCount = queueItems.filter((item) => item.status === "blocked").length;
  const criticalCount = queueItems.filter((item) => item.priority === "critical").length;

  return [
    {
      label: "Total exposure",
      value: formatMoney(snapshot.total_exposure_cents),
      trend: `${queueItems.length} live queue item${queueItems.length === 1 ? "" : "s"} in the latest snapshot`,
      change: formatTimestampLabel(snapshot.generated_at) ?? "Live snapshot",
      drillLabel: "Review current queue",
    },
    {
      label: "30-day recovery",
      value: formatMoney(snapshot.expected_recovery_30_day_cents),
      trend: "Projected recovery in the next 30 days",
      change: formatMoney(snapshot.short_term_cash_opportunity_cents),
      drillLabel: "Inspect recovery work",
    },
    {
      label: "High-risk claims",
      value: String(snapshot.high_risk_claim_count),
      trend: `${blockedCount} denied claim${blockedCount === 1 ? "" : "s"} currently surfaced`,
      change: `${criticalCount} critical`,
      drillLabel: "Open denied claims",
    },
    {
      label: "Critical pre-submission",
      value: String(snapshot.critical_pre_submission_count),
      trend: "Pre-submission issues flagged by the backend",
      change: snapshot.top_worklist.length > 0 ? `${snapshot.top_worklist.length} prioritized` : "No worklist items",
      drillLabel: "Focus urgent work",
    },
  ];
}

export function buildPipelineStages(queueItems: QueueItem[]): PipelineStage[] {
  const criticalCount = queueItems.filter((item) => item.priority === "critical").length;
  const blockedCount = queueItems.filter((item) => item.status === "blocked").length;
  const openBalanceCount = queueItems.filter((item) => item.queue === "Open balances").length;
  const agedCount = queueItems.filter((item) => item.agingDays >= 90).length;
  const resolvedCount = queueItems.filter((item) => item.status === "resolved").length;

  return [
    { label: "Critical now", count: criticalCount, tone: criticalCount > 0 ? "warning" : "good", action: "Prioritize urgent claims" },
    { label: "Denied claims", count: blockedCount, tone: blockedCount > 0 ? "warning" : "neutral", action: "Review denial follow-up" },
    { label: "Open balances", count: openBalanceCount, tone: openBalanceCount > 0 ? "neutral" : "good", action: "Work active balances" },
    { label: "Aged 90+ days", count: agedCount, tone: agedCount > 0 ? "warning" : "good", action: "Escalate older claims" },
    { label: "Resolved", count: resolvedCount, tone: "good", action: "Verify settled claims" },
  ];
}

export function buildPolicyRules(queueItems: QueueItem[]): PolicyRule[] {
  const deniedCount = queueItems.filter((item) => item.status === "blocked").length;
  const agedCount = queueItems.filter((item) => item.agingDays >= 90).length;
  const openBalanceCount = queueItems.filter((item) => item.queue === "Open balances").length;

  return [
    {
      id: "POL-LIVE-01",
      name: "Denied claim follow-up",
      condition: "If live claim status = DENIED",
      outcome: "Keep the claim in the blocked queue until an operator resolves the next denial action.",
      coverage: `${deniedCount} live claim${deniedCount === 1 ? "" : "s"}`,
    },
    {
      id: "POL-LIVE-02",
      name: "Aging escalation",
      condition: "If claim aging >= 90 days",
      outcome: "Promote the claim so older balances surface earlier in the work queue.",
      coverage: `${agedCount} live claim${agedCount === 1 ? "" : "s"}`,
    },
    {
      id: "POL-LIVE-03",
      name: "Open balance review",
      condition: "If live claim status = OPEN or PARTIAL",
      outcome: "Route the claim into active follow-up until payment or denial resolution is documented.",
      coverage: `${openBalanceCount} live claim${openBalanceCount === 1 ? "" : "s"}`,
    },
  ];
}

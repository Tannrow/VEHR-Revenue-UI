import { apiFetch } from "@/lib/api";

export type FinanceAIRecommendedAction = {
  action: string;
  impact_estimate: string;
  urgency: "high" | "medium" | "low";
};

export type FinanceAIDraft = {
  type: string;
  content: string;
};

export type FinanceAIResponse = {
  summary: string;
  root_cause: string;
  recommended_actions: FinanceAIRecommendedAction[];
  drafts: FinanceAIDraft[];
  questions_needed: string[];
  assumptions: string[];
  data_used: unknown;
  confidence: "low" | "medium" | "high";
};

export type FinanceAIEnvelope = {
  context_pack_version: string;
  generated_at: string;
  risk_score: string;
  advisory: FinanceAIResponse;
};

function ensureArray<T>(value: unknown, fallback: T[]): T[] {
  return Array.isArray(value) ? (value as T[]) : fallback;
}

function ensureString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function ensureConfidence(value: unknown): "low" | "medium" | "high" {
  if (value === "high" || value === "medium" || value === "low") return value;
  return "medium";
}

export function normalizeFinanceAIEnvelope(payload: unknown): FinanceAIEnvelope {
  if (!payload || typeof payload !== "object") {
    return {
      context_pack_version: "unknown",
      generated_at: new Date().toISOString(),
      risk_score: "0.00",
      advisory: {
        summary: "No advisory available",
        root_cause: "Missing data from service",
        recommended_actions: [],
        drafts: [],
        questions_needed: [],
        assumptions: [],
        data_used: {},
        confidence: "medium",
      },
    };
  }
  const advisory = (payload as { advisory?: unknown }).advisory ?? {};
  const recommendedActions = ensureArray<FinanceAIRecommendedAction>(
    (advisory as { recommended_actions?: unknown }).recommended_actions,
    [],
  ).map((item) => ({
    action: ensureString((item as FinanceAIRecommendedAction).action, "Action pending"),
    impact_estimate: ensureString((item as FinanceAIRecommendedAction).impact_estimate, "0"),
    urgency: ensureConfidence((item as FinanceAIRecommendedAction).urgency),
  }));

  const drafts = ensureArray<FinanceAIDraft>((advisory as { drafts?: unknown }).drafts, []).map((draft) => ({
    type: ensureString((draft as FinanceAIDraft).type, "note"),
    content: ensureString((draft as FinanceAIDraft).content, ""),
  }));

  const response: FinanceAIResponse = {
    summary: ensureString((advisory as { summary?: unknown }).summary, ""),
    root_cause: ensureString((advisory as { root_cause?: unknown }).root_cause, ""),
    recommended_actions: recommendedActions,
    drafts,
    questions_needed: ensureArray<string>((advisory as { questions_needed?: unknown }).questions_needed, []),
    assumptions: ensureArray<string>((advisory as { assumptions?: unknown }).assumptions, []),
    data_used: (advisory as { data_used?: unknown }).data_used ?? {},
    confidence: ensureConfidence((advisory as { confidence?: unknown }).confidence),
  };

  return {
    context_pack_version: ensureString((payload as { context_pack_version?: unknown }).context_pack_version, "unknown"),
    generated_at: ensureString((payload as { generated_at?: unknown }).generated_at, new Date().toISOString()),
    risk_score: ensureString((payload as { risk_score?: unknown }).risk_score, "0.00"),
    advisory: response,
  };
}

export async function fetchFinanceInsight(path: string, body: unknown): Promise<FinanceAIEnvelope> {
  const payload = await apiFetch<unknown>(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
    cache: "no-store",
  });
  return normalizeFinanceAIEnvelope(payload);
}

import { apiClientFetch } from "@/lib/api/client";
import { isFetchFailedMessage } from "@/lib/error-messages";

export type ClaimRecord = {
  id?: string;
  external_claim_id?: string | null;
  patient_name?: string | null;
  payer_name?: string | null;
  status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ClaimsState = {
  claims: ClaimRecord[];
  error: string | null;
};

export function isClaimRecord(value: unknown): value is ClaimRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function formatClaimsError(status: number, payload: unknown, text: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return isFetchFailedMessage(payload) ? "Unable to reach the VEHR claims endpoint right now." : payload.trim();
  }

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

  if (text.trim()) {
    return text.trim();
  }

  return `Unable to load claims (status ${status}).`;
}

export async function fetchClaimsIndex(): Promise<ClaimsState> {
  try {
    const response = await apiClientFetch("/api/claims");

    if (!response.ok) {
      return {
        claims: [],
        error: formatClaimsError(response.status, response.data, response.text),
      };
    }

    const claims = Array.isArray(response.data) ? response.data.filter(isClaimRecord) : [];

    return {
      claims,
      error: null,
    };
  } catch (error) {
    return {
      claims: [],
      error:
        error instanceof Error && !isFetchFailedMessage(error.message)
          ? error.message
          : "Unable to load claims right now.",
    };
  }
}

import { ZodError } from "zod";

import { apiClientFetch, logApiFailure } from "@/lib/api/client";
import {
  apiErrorResponseSchema,
  revenueSnapshotMissingSchema,
  revenueSnapshotResponseSchema,
  type ApiErrorResponse,
  type RevenueSnapshotMissing,
  type RevenueSnapshotResponse,
} from "@/lib/api/types";
import { isFetchFailedMessage } from "@/lib/error-messages";

export const LATEST_REVENUE_SNAPSHOT_BACKEND_PATH = "/api/v1/revenue/snapshots/latest";
export const LATEST_REVENUE_SNAPSHOT_API_PATH = "/api/dashboard";
export const SNAPSHOT_MISSING_REFRESH_INTERVAL_MS = 30_000;

export type DashboardState =
  | { status: "loading" }
  | { status: "snapshot_missing"; detail: RevenueSnapshotMissing }
  | { status: "ready"; snapshot: RevenueSnapshotResponse }
  | { status: "error"; error: string; detail?: ApiErrorResponse; code?: number }
  | { status: "unauthorized"; error: string; detail?: ApiErrorResponse; code: 401 | 403 };

function normalizeErrorMessage(message: string, fallback: string): string {
  const trimmedMessage = message.trim();

  if (!trimmedMessage) {
    return fallback;
  }

  return isFetchFailedMessage(trimmedMessage) ? fallback : trimmedMessage;
}

function getApiErrorResponse(payload: unknown, text: string, fallback: string): ApiErrorResponse {
  const parsedError = apiErrorResponseSchema.safeParse(payload);

  if (parsedError.success) {
    return parsedError.data;
  }

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const record = payload as Record<string, unknown>;
    const message = [record.error, record.detail, record.message].find(
      (value): value is string => typeof value === "string" && value.trim().length > 0,
    );

    if (message) {
      return {
        error: normalizeErrorMessage(message, fallback),
      };
    }
  }

  const normalizedText = normalizeErrorMessage(text, fallback);

  return {
    error: normalizedText,
  };
}

function getSchemaError(error: ZodError, fallback: string): ApiErrorResponse {
  return {
    error: fallback,
    detail: error.issues.map((issue) => issue.message).join("; "),
  };
}

export async function fetchLatestRevenueSnapshotState(): Promise<Exclude<DashboardState, { status: "loading" }>> {
  try {
    const response = await apiClientFetch(LATEST_REVENUE_SNAPSHOT_API_PATH);

    if (response.ok) {
      const parsedSnapshot = revenueSnapshotResponseSchema.safeParse(response.data);

      if (parsedSnapshot.success) {
        return {
          status: "ready",
          snapshot: parsedSnapshot.data,
        };
      }

      const detail = getSchemaError(parsedSnapshot.error, "Revenue snapshot data did not match the expected contract.");
      logApiFailure({
        route: LATEST_REVENUE_SNAPSHOT_API_PATH,
        status: response.status,
        reason: detail.error,
        detail: detail.detail,
      });

      return {
        status: "error",
        error: detail.error,
        detail,
        code: response.status,
      };
    }

    if (response.status === 404) {
      const parsedMissing = revenueSnapshotMissingSchema.safeParse(response.data);

      if (parsedMissing.success) {
        logApiFailure({
          route: LATEST_REVENUE_SNAPSHOT_API_PATH,
          status: response.status,
          reason: parsedMissing.data.error,
          detail: parsedMissing.data.detail,
        });

        return {
          status: "snapshot_missing",
          detail: parsedMissing.data,
        };
      }
    }

    const fallbackError =
      response.status === 401 || response.status === 403
        ? "Your session has expired. Redirecting to login."
        : `Unable to load dashboard data (status ${response.status}).`;
    const detail = getApiErrorResponse(response.data, response.text, fallbackError);

    logApiFailure({
      route: LATEST_REVENUE_SNAPSHOT_API_PATH,
      status: response.status,
      reason: detail.error,
      detail: detail.detail ?? detail.message,
    });

    if (response.status === 401 || response.status === 403) {
      return {
        status: "unauthorized",
        error: detail.error,
        detail,
        code: response.status,
      };
    }

    return {
      status: "error",
      error: detail.error,
      detail,
      code: response.status,
    };
  } catch (error) {
    const message =
      error instanceof Error
        ? normalizeErrorMessage(error.message, "Unable to load dashboard data right now.")
        : "Unable to load dashboard data right now.";

    logApiFailure({
      route: LATEST_REVENUE_SNAPSHOT_API_PATH,
      reason: message,
    });

    return {
      status: "error",
      error: message,
    };
  }
}

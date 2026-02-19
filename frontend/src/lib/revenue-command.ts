import { apiFetch } from "@/lib/api";
import type { RevenueSnapshot } from "@/types/revenueSnapshot";

export type { RevenueSnapshot };
export type { RevenueSnapshotAggressivePayer, RevenueSnapshotWorklistItem } from "@/types/revenueSnapshot";

export async function fetchLatestRevenueSnapshot(): Promise<RevenueSnapshot> {
  return apiFetch<RevenueSnapshot>("/api/v1/revenue/snapshots/latest", { cache: "no-store" });
}

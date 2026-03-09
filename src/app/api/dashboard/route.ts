import { NextResponse } from "next/server";

import { discoverBackendPath, proxyBackendGet } from "@/lib/backend";

export const dynamic = "force-dynamic";

const DASHBOARD_FALLBACK_PATHS = [
  "/dashboard/summary",
  "/dashboard",
  "/summary",
  "/metrics/summary",
] as const;

export async function GET() {
  try {
    const backendPath = await discoverBackendPath({
      method: "get",
      preferredPaths: DASHBOARD_FALLBACK_PATHS,
      keywords: ["dashboard", "summary", "metric", "overview"],
    });

    return await proxyBackendGet(backendPath);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to proxy dashboard request.",
      },
      { status: 502 },
    );
  }
}

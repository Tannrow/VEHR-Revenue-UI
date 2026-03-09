import { NextResponse } from "next/server";

import { discoverBackendPath, proxyBackendGet } from "@/lib/backend";

export const dynamic = "force-dynamic";

const CLAIMS_FALLBACK_PATHS = ["/claims", "/api/claims", "/claims/list"] as const;

export async function GET() {
  try {
    const backendPath = await discoverBackendPath({
      method: "get",
      preferredPaths: CLAIMS_FALLBACK_PATHS,
      keywords: ["claim", "claims", "list"],
    });

    return await proxyBackendGet(backendPath);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to proxy claims request.",
      },
      { status: 502 },
    );
  }
}

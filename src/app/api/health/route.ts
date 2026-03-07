import { NextResponse } from "next/server";

import { getBackendBaseUrl, probeBackendHealth } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  const health = await probeBackendHealth();

  return NextResponse.json(
    {
      backendUrl: getBackendBaseUrl(),
      ...health,
    },
    {
      status: health.connected ? 200 : 503,
    },
  );
}

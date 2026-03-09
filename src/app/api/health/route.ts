import { NextResponse } from "next/server";

import { getBackendBaseUrl, proxyBackendGet } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const healthResponse = await proxyBackendGet("/health");

    if (healthResponse.status !== 404) {
      return healthResponse;
    }
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        backendUrl: getBackendBaseUrl(),
        error: error instanceof Error ? error.message : "Unable to reach backend health endpoint.",
      },
      { status: 502 },
    );
  }

  try {
    // Some deployments expose Swagger docs but not a dedicated /health endpoint.
    const docsResponse = await proxyBackendGet("/docs");

    return NextResponse.json(
      {
        ok: docsResponse.ok,
        backendUrl: getBackendBaseUrl(),
        proxiedPath: "/docs",
      },
      { status: docsResponse.status },
    );
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        backendUrl: getBackendBaseUrl(),
        error: error instanceof Error ? error.message : "Unable to reach backend docs endpoint.",
      },
      { status: 502 },
    );
  }
}

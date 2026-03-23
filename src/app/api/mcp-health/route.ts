import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { getAccessToken, withAccessToken } from "@/lib/auth";
import { isFetchFailedMessage } from "@/lib/error-messages";

export const dynamic = "force-dynamic";

export async function GET() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return NextResponse.json({ detail: "Missing credentials" }, { status: 401 });
  }

  try {
    return await proxyBackendResponse("/api/v1/admin/integrations/mcp-health", {
      headers: withAccessToken(undefined, accessToken),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR MCP diagnostics endpoint.",
      },
      { status: 502 },
    );
  }
}

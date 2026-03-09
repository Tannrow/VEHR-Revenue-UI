import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { getAccessToken, withAccessToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return await proxyBackendResponse("/api/v1/revenue/snapshots/latest", {
      headers: withAccessToken(undefined, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR dashboard endpoint.",
      },
      { status: 502 },
    );
  }
}

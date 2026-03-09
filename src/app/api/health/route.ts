import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return await proxyBackendResponse("/api/v1/health");
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR health endpoint.",
      },
      { status: 502 },
    );
  }
}

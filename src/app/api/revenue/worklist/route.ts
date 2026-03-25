import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { getAccessToken, withAccessToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

const BACKEND_PATH = "/api/v1/revenue/worklist";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const backendPath = url.search ? `${BACKEND_PATH}${url.search}` : BACKEND_PATH;
    return await proxyBackendResponse(backendPath, {
      headers: withAccessToken(undefined, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR revenue worklist endpoint.",
      },
      { status: 502 },
    );
  }
}

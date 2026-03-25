import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { getAccessToken, withAccessToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

const BACKEND_PATH = "/api/v1/revenue/worklist/actions";

export async function POST(request: Request) {
  try {
    return await proxyBackendResponse(BACKEND_PATH, {
      method: "POST",
      body: await request.text(),
      headers: withAccessToken(
        {
          "content-type": "application/json",
        },
        await getAccessToken(),
      ),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR revenue worklist action endpoint.",
      },
      { status: 502 },
    );
  }
}

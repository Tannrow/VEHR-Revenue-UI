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
    return await proxyBackendResponse("/api/v1/auth/me", {
      headers: withAccessToken(undefined, accessToken),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR auth endpoint.",
      },
      { status: 502 },
    );
  }
}

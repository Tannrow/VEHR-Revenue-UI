import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { getAccessToken, withAccessToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    eraFileId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { eraFileId } = await context.params;

  try {
    return await proxyBackendResponse(`/api/v1/revenue/era-pdfs/${eraFileId}/replay-preview`, {
      method: "POST",
      body: await request.text(),
      headers: withAccessToken({ "content-type": "application/json" }, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR ERA replay preview endpoint.",
      },
      { status: 502 },
    );
  }
}

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

export async function GET(_: Request, context: RouteContext) {
  const { eraFileId } = await context.params;

  try {
    return await proxyBackendResponse(`/api/v1/revenue/era-pdfs/${eraFileId}/lab`, {
      headers: withAccessToken(undefined, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR ERA lab endpoint.",
      },
      { status: 502 },
    );
  }
}

import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";
import { getAccessToken, withAccessToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return await proxyBackendResponse("/api/v1/revenue/era-pdfs", {
      headers: withAccessToken(undefined, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR ERA list endpoint.",
      },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  try {
    return await proxyBackendResponse("/api/v1/revenue/era-pdfs/upload", {
      method: "POST",
      body: await request.formData(),
      headers: withAccessToken(undefined, await getAccessToken()),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR ERA upload endpoint.",
      },
      { status: 502 },
    );
  }
}

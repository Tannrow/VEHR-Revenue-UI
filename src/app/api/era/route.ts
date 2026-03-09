import { NextResponse } from "next/server";

import { proxyBackendResponse } from "@/lib/backend";
import { isFetchFailedMessage } from "@/lib/error-messages";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    return await proxyBackendResponse("/api/v1/revenue/era-pdfs/upload", {
      method: "POST",
      body: await request.formData(),
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

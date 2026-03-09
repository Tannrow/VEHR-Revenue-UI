import { NextResponse } from "next/server";

import { discoverBackendPath, proxyBackendMultipartPost } from "@/lib/backend";

export const dynamic = "force-dynamic";

const ERA_FALLBACK_PATHS = ["/era/upload", "/era", "/remittance/upload"] as const;

export async function POST(request: Request) {
  try {
    const backendPath = await discoverBackendPath({
      method: "post",
      preferredPaths: ERA_FALLBACK_PATHS,
      keywords: ["era", "upload", "remittance"],
      requireMultipart: true,
    });

    return await proxyBackendMultipartPost(backendPath, await request.formData());
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to proxy ERA upload.",
      },
      { status: 502 },
    );
  }
}

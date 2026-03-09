import { NextResponse } from "next/server";

import { ACCESS_TOKEN_COOKIE_NAME, getAccessTokenCookieOptions } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST() {
  const response = NextResponse.json({ success: true });

  response.cookies.set(ACCESS_TOKEN_COOKIE_NAME, "", {
    ...getAccessTokenCookieOptions(),
    maxAge: 0,
  });

  return response;
}

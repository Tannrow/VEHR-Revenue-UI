import { cookies } from "next/headers";

export const ACCESS_TOKEN_COOKIE_NAME = "vehr_access_token";

export function getAccessTokenCookieOptions() {
  return {
    httpOnly: true,
    path: "/",
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
  };
}

export async function getAccessToken(): Promise<string | null> {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE_NAME)?.value;
  const normalizedAccessToken = accessToken?.trim();

  return normalizedAccessToken ? normalizedAccessToken : null;
}

export function withAccessToken(headersInit: HeadersInit | undefined, accessToken: string | null): Headers {
  const headers = new Headers(headersInit);

  if (accessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return headers;
}

export function extractAccessToken(payload: unknown): string | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }

  const accessToken = (payload as Record<string, unknown>).access_token;

  return typeof accessToken === "string" && accessToken.trim() ? accessToken : null;
}

import { NextResponse } from "next/server";

import { BackendFetchError, backendFetch } from "@/lib/backend";
import {
  ACCESS_TOKEN_COOKIE_NAME,
  extractAccessToken,
  getAccessTokenCookieOptions,
} from "@/lib/auth";
import { isFetchFailedMessage } from "@/lib/error-messages";
import {
  INVALID_LOGIN_REQUEST_ERROR,
  LOGIN_REQUEST_CONTENT_TYPE,
  normalizeLoginCredentials,
  serializeLoginRequestBody,
} from "@/lib/login";

export const dynamic = "force-dynamic";

function getProxyErrorResponse(error: BackendFetchError): Response {
  return new Response(error.responseText, {
    status: error.status,
    headers: error.contentType ? { "content-type": error.contentType } : undefined,
  });
}

function tryParseJson(value: string): { parsed: boolean; payload: unknown } {
  if (!value.trim()) {
    return {
      parsed: true,
      payload: null,
    };
  }

  try {
    return {
      parsed: true,
      payload: JSON.parse(value) as unknown,
    };
  } catch {
    return {
      parsed: false,
      payload: null,
    };
  }
}

export async function POST(request: Request) {
  let payload: unknown;

  try {
    payload = (await request.json()) as unknown;
  } catch {
    return NextResponse.json(
      {
        error: "Login request body must be valid JSON.",
      },
      { status: 400 },
    );
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return NextResponse.json(
      {
        error: INVALID_LOGIN_REQUEST_ERROR,
      },
      { status: 400 },
    );
  }

  const payloadRecord = payload as Record<string, unknown>;
  const credentials = normalizeLoginCredentials({
    username: payloadRecord.username,
    password: payloadRecord.password,
  });

  if (!credentials) {
    return NextResponse.json(
      {
        error: INVALID_LOGIN_REQUEST_ERROR,
      },
      { status: 400 },
    );
  }

  try {
    const response = await backendFetch("/api/v1/auth/login", {
      method: "POST",
      body: serializeLoginRequestBody(credentials),
      headers: { "content-type": LOGIN_REQUEST_CONTENT_TYPE },
    });
    const responseText = await response.text();
    const parsedResponse = tryParseJson(responseText);
    const accessToken = extractAccessToken(parsedResponse.payload);

    if (!accessToken) {
      return NextResponse.json(
        {
          error: parsedResponse.parsed
            ? "Login failed: backend response missing access_token."
            : "Login failed: backend response was not valid JSON.",
        },
        { status: 502 },
      );
    }

    const successResponse = NextResponse.json({ success: true });
    successResponse.cookies.set(ACCESS_TOKEN_COOKIE_NAME, accessToken, getAccessTokenCookieOptions());

    return successResponse;
  } catch (error) {
    if (error instanceof BackendFetchError) {
      return getProxyErrorResponse(error);
    }

    return NextResponse.json(
      {
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to reach the VEHR login endpoint.",
      },
      { status: 502 },
    );
  }
}

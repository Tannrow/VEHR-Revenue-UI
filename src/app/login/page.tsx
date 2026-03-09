"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageShell, SectionCard } from "@/components/page-shell";
import { isFetchFailedMessage } from "@/lib/error-messages";
import {
  LOGIN_REQUEST_CONTENT_TYPE,
  normalizeLoginCredentials,
  serializeLoginRequestBody,
} from "@/lib/login";

type LoginState = {
  status: "idle" | "submitting" | "error";
  error: string | null;
};

const INITIAL_STATE: LoginState = {
  status: "idle",
  error: null,
};

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getValidationDetailMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return typeof detail === "string" && detail.trim() ? detail.trim() : null;
  }

  const message = detail.find(
    (item): item is JsonRecord => isRecord(item) && typeof item.msg === "string" && item.msg.trim().length > 0,
  )?.msg;

  if (typeof message !== "string") {
    return null;
  }

  const trimmedMessage = message.trim();

  return trimmedMessage ? trimmedMessage : null;
}

function getErrorMessage(status: number, payload: unknown, text: string): string {
  if (isRecord(payload)) {
    const errorMessage = payload.error;
    const detailMessage = getValidationDetailMessage(payload.detail);
    const message = typeof errorMessage === "string" ? errorMessage : detailMessage;

    if (typeof message === "string" && message.trim()) {
      return message.trim();
    }
  }

  if (text.trim()) {
    return text.trim();
  }

  if (status === 401 || status === 403) {
    return "Sign in failed. Check your username and password and try again.";
  }

  return "Unable to sign in right now.";
}

export default function LoginPage() {
  const router = useRouter();
  const [state, setState] = useState<LoginState>(INITIAL_STATE);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = event.currentTarget;
    const formData = new FormData(form);
    const credentials = normalizeLoginCredentials({
      username: formData.get("username"),
      password: formData.get("password"),
    });

    if (!credentials) {
      setState({
        status: "error",
        error: "Enter both your username and password.",
      });
      return;
    }

    setState({
      status: "submitting",
      error: null,
    });

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": LOGIN_REQUEST_CONTENT_TYPE,
        },
        body: serializeLoginRequestBody(credentials),
      });
      const contentType = response.headers.get("content-type") ?? "";
      const text = await response.text();
      const payload =
        contentType.includes("application/json") && text
          ? (JSON.parse(text) as unknown)
          : null;

      if (!response.ok) {
        setState({
          status: "error",
          error: getErrorMessage(response.status, payload, text),
        });
        return;
      }

      setState(INITIAL_STATE);
      router.push("/dashboard");
      router.refresh();
    } catch (error) {
      setState({
        status: "error",
        error:
          error instanceof Error && !isFetchFailedMessage(error.message)
            ? error.message
            : "Unable to sign in right now.",
      });
    }
  }

  return (
    <PageShell
      title="Sign in"
      description="Sign in with your VEHR credentials to access protected revenue workflows."
      footer="Authentication is proxied through /api/auth/login on the UI origin."
    >
      <SectionCard title="Account access">
        <div className="space-y-6 text-sm text-zinc-300">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label htmlFor="username" className="block text-sm font-medium text-zinc-200">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                className="block w-full rounded-md border border-zinc-700 bg-black/50 px-3 py-2 text-zinc-200"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium text-zinc-200">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="block w-full rounded-md border border-zinc-700 bg-black/50 px-3 py-2 text-zinc-200"
              />
            </div>

            <button
              type="submit"
              disabled={state.status === "submitting"}
              className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:border-zinc-700 disabled:text-zinc-500"
            >
              {state.status === "submitting" ? "Signing in..." : "Sign in"}
            </button>
          </form>

          {state.error ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200">
              {state.error}
            </p>
          ) : null}

          <Link
            href="/"
            className="inline-flex rounded-md border border-zinc-700 px-4 py-2 text-white transition hover:border-white"
          >
            Back to home
          </Link>
        </div>
      </SectionCard>
    </PageShell>
  );
}

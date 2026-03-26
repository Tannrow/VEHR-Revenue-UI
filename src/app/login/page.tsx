"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

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

  for (const item of detail) {
    if (!isRecord(item) || typeof item.msg !== "string") {
      continue;
    }

    const trimmedMessage = item.msg.trim();
    if (trimmedMessage) {
      return trimmedMessage;
    }
  }

  return null;
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
    return "Sign in failed. Check your email and password and try again.";
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
      email: formData.get("email"),
      password: formData.get("password"),
    });

    if (!credentials) {
      setState({
        status: "error",
        error: "Enter both your email and password.",
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
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(110,168,254,0.12),transparent_26%),linear-gradient(180deg,#0c1017,#090c12)] text-white">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-5 py-10 md:px-8">
        <div className="grid w-full gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="flex flex-col justify-between rounded-[32px] border border-white/8 bg-[linear-gradient(180deg,rgba(21,25,34,0.94),rgba(14,17,24,0.98))] p-8 shadow-[0_28px_120px_rgba(0,0,0,0.45)] backdrop-blur-sm md:p-10">
            <div className="space-y-6">
              <div className="inline-flex w-fit items-center rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] uppercase tracking-[0.34em] text-slate-400">
                VEHR Revenue OS
              </div>
              <div className="space-y-4">
                <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.05em] text-white md:text-[3.5rem]">
                  Dedicated operator sign in.
                </h1>
                <p className="max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
                  Sign in with your VEHR credentials to open the canonical backend work queue, ERA replay lab,
                  diagnostics, and claims workflows.
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {[
                  {
                    title: "Backend-owned worklist",
                    body: "Priority, SLA, escalation, and recommended actions now come from the backend worklist contract.",
                  },
                  {
                    title: "ERA replay lab",
                    body: "Inspect OCR, deterministic parsing, merge behavior, and preview normalization on the same file.",
                  },
                  {
                    title: "Diagnostics",
                    body: "Check Azure, Document Intelligence, and OpenAI runtime status from the authenticated console.",
                  },
                  {
                    title: "Thin operator console",
                    body: "The UI renders canonical backend state instead of inventing queue logic in the browser.",
                  },
                ].map((item) => (
                  <div key={item.title} className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
                    <h2 className="text-base font-semibold text-white">{item.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{item.body}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-3 text-sm text-slate-400">
              <Link
                href="/"
                className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 font-medium text-white hover:-translate-y-[1px] hover:border-white/18 hover:bg-white/[0.08]"
              >
                Back to home
              </Link>
              <span>Authentication is proxied through `/api/auth/login` on the UI origin.</span>
            </div>
          </section>

          <section className="rounded-[32px] border border-white/8 bg-[linear-gradient(180deg,rgba(15,18,25,0.96),rgba(10,13,19,0.98))] p-8 shadow-[0_28px_120px_rgba(0,0,0,0.45)] backdrop-blur-sm md:p-10">
            <div className="space-y-6">
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-[0.32em] text-slate-500">Account access</p>
                <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">Sign in</h2>
                <p className="text-sm leading-6 text-slate-400">
                  Use your VEHR credentials to access protected revenue workflows.
                </p>
              </div>

              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2">
                  <label htmlFor="email" className="block text-sm font-medium text-zinc-200">
                    Email
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="block w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-base text-zinc-100 outline-none transition focus:border-sky-400/60 focus:bg-black/40 md:text-sm"
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
                    className="block w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-base text-zinc-100 outline-none transition focus:border-sky-400/60 focus:bg-black/40 md:text-sm"
                  />
                </div>

                <button
                  type="submit"
                  disabled={state.status === "submitting"}
                  className="inline-flex w-full items-center justify-center rounded-2xl border border-sky-300/20 bg-sky-300/10 px-4 py-3 font-medium text-sky-100 transition hover:-translate-y-[1px] hover:border-sky-200/30 hover:bg-sky-300/16 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.04] disabled:text-slate-500"
                >
                  {state.status === "submitting" ? "Signing in..." : "Sign in"}
                </button>
              </form>

              {state.error ? (
                <p className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                  {state.error}
                </p>
              ) : null}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

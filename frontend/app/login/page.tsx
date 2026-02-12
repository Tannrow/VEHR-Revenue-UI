"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { persistAccessToken } from "@/lib/auth";
import { fetchMePreferences, resolvePostLoginRoute } from "@/lib/preferences";

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  organization_id: string;
  user_id: string;
};

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

function resolveNextPath(value: string | null): string | null {
  if (!value || !value.startsWith("/")) {
    return null;
  }
  return value;
}

export default function LoginPage() {
  const router = useRouter();
  const [requestedNextPath, setRequestedNextPath] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [needsOrganizationId, setNeedsOrganizationId] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRequestedNextPath(resolveNextPath(new URLSearchParams(window.location.search).get("next")));
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function checkExistingSession() {
      try {
        await apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" });
        const preferences = await fetchMePreferences();
        if (!isMounted) return;
        router.replace(resolvePostLoginRoute(preferences, requestedNextPath));
      } catch {
        if (!isMounted) return;
      } finally {
        if (isMounted) {
          setIsCheckingSession(false);
        }
      }
    }

    checkExistingSession();
    return () => {
      isMounted = false;
    };
  }, [requestedNextPath, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedPassword = password.trim();
    if (!normalizedEmail || !normalizedPassword) {
      setError("Email and password are required.");
      return;
    }

    if (needsOrganizationId && !organizationId.trim()) {
      setError("Organization ID is required for your account.");
      return;
    }

    try {
      setIsSubmitting(true);
      const payload: { email: string; password: string; organization_id?: string } = {
        email: normalizedEmail,
        password: normalizedPassword,
      };
      if (organizationId.trim()) {
        payload.organization_id = organizationId.trim();
      }

      const response = await apiFetch<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      persistAccessToken(response.access_token);
      const preferences = await fetchMePreferences();
      router.replace(resolvePostLoginRoute(preferences, requestedNextPath));
    } catch (submitError) {
      const message = submitError instanceof ApiError || submitError instanceof Error
        ? submitError.message || "Login failed."
        : "Login failed.";
      if (message.toLowerCase().includes("organization_id required")) {
        setNeedsOrganizationId(true);
        setError("Please enter your organization ID to continue.");
      } else {
        setError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-100 px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(15,23,42,0.08),_transparent_42%),radial-gradient(circle_at_80%_20%,_rgba(14,116,144,0.12),_transparent_36%),linear-gradient(180deg,_#f8fafc_0%,_#eef2f7_100%)]" />

      <div className="relative z-10 w-full max-w-md">
        <div className="rounded-2xl border border-slate-200 bg-white/95 px-7 py-8 shadow-[0_20px_40px_-20px_rgba(15,23,42,0.35)] backdrop-blur">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-sm font-bold tracking-[0.18em] text-white">
              E360
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Encompass 360</h1>
            <p className="mt-1 text-sm text-slate-600">For clinicians. By clinicians.</p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            {isCheckingSession ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                Checking existing session...
              </div>
            ) : null}

            {error ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </div>
            ) : null}

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@encompass360.com"
                autoComplete="email"
                className="h-11 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="h-11 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
                required
              />
            </div>

            {needsOrganizationId ? (
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500" htmlFor="organization_id">
                  Organization ID
                </label>
                <input
                  id="organization_id"
                  type="text"
                  value={organizationId}
                  onChange={(event) => setOrganizationId(event.target.value)}
                  className="h-11 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  required
                />
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting || isCheckingSession}
              className="inline-flex h-11 w-full items-center justify-center rounded-lg bg-slate-900 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-65"
            >
              {isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

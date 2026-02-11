"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { persistAccessToken } from "@/lib/auth";
import { BRANDING } from "@/lib/branding";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

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

function resolveNextPath(value: string | null): string {
  if (!value || !value.startsWith("/")) {
    return "/dashboard";
  }
  return value;
}

export default function LoginPage() {
  const router = useRouter();
  const [nextPath, setNextPath] = useState("/dashboard");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNextPath(resolveNextPath(new URLSearchParams(window.location.search).get("next")));
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function checkExistingSession() {
      try {
        await apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" });
        if (!isMounted) return;
        router.replace(nextPath);
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
  }, [nextPath, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedPassword = password.trim();
    if (!normalizedEmail || !normalizedPassword) {
      setError("Email and password are required.");
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
      router.replace(nextPath);
    } catch (submitError) {
      if (submitError instanceof ApiError || submitError instanceof Error) {
        setError(submitError.message || "Login failed.");
      } else {
        setError("Login failed.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen px-6 py-16 sm:px-10">
      <div className="mx-auto grid w-full max-w-5xl gap-6 lg:grid-cols-[1.15fr_1fr]">
        <Card className="bg-white shadow-sm">
          <CardHeader className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
              {BRANDING.name}
            </p>
            <CardTitle className="text-3xl tracking-tight text-slate-900">
              Sign in to {BRANDING.name}
            </CardTitle>
            <p className="text-sm text-slate-500">
              {BRANDING.tagline}
            </p>
          </CardHeader>
          <CardContent>
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
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="email">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="clinician@your-org.com"
                  autoComplete="email"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="organization_id">
                  Organization ID
                </label>
                <Input
                  id="organization_id"
                  value={organizationId}
                  onChange={(event) => setOrganizationId(event.target.value)}
                  placeholder="Optional unless user belongs to multiple organizations"
                />
              </div>

              <Button type="submit" className="h-10 w-full rounded-lg" disabled={isSubmitting || isCheckingSession}>
                {isSubmitting ? "Signing in..." : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg text-slate-900">Access Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600">
            <p>Tokens are saved in browser storage for this workspace session.</p>
            <p>
              If login returns an organization selection error, re-submit with your
              `organization_id`.
            </p>
            <p>After successful login you will be redirected to your CRM workspace.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

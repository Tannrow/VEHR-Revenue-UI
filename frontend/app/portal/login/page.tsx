"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  PortalApiError,
  clearPortalAccessToken,
  persistPortalAccessToken,
  portalFetch,
} from "@/lib/portal";

type PortalLoginResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  patient_id: string;
  organization_id: string;
};

function getMagicTokenFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  return params.get("magic_token");
}

export default function PortalLoginPage() {
  const router = useRouter();
  const [patientId, setPatientId] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [magicToken, setMagicToken] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    clearPortalAccessToken();
    setMagicToken(getMagicTokenFromLocation());
  }, []);

  const canUseMagicLink = useMemo(
    () => typeof magicToken === "string" && magicToken.length > 0,
    [magicToken],
  );

  async function submit(payload: Record<string, unknown>) {
    try {
      setIsSubmitting(true);
      setError(null);
      const response = await portalFetch<PortalLoginResponse>("/api/v1/portal/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      persistPortalAccessToken(response.access_token);
      router.replace("/portal");
    } catch (submitError) {
      if (submitError instanceof PortalApiError || submitError instanceof Error) {
        setError(submitError.message || "Portal login failed");
      } else {
        setError("Portal login failed");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCodeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedCode = code.trim();
    if (!normalizedCode) {
      setError("Access code is required.");
      return;
    }
    if (!patientId.trim() && !email.trim()) {
      setError("Patient ID or email is required.");
      return;
    }
    await submit({
      code: normalizedCode,
      patient_id: patientId.trim() || undefined,
      email: email.trim().toLowerCase() || undefined,
    });
  }

  async function handleMagicLinkSubmit() {
    if (!canUseMagicLink || !magicToken) return;
    await submit({ magic_token: magicToken });
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-4xl items-center px-4 py-8 sm:px-8">
      <div className="grid w-full gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Card className="border-slate-200/70 bg-white/95 shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
          <CardHeader className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
              Patient Portal
            </p>
            <CardTitle className="text-3xl tracking-tight text-slate-900">
              Complete Your Forms
            </CardTitle>
            <p className="text-sm text-slate-500">
              Sign in with your portal code or secure magic link.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {error ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </div>
            ) : null}

            {canUseMagicLink ? (
              <div className="rounded-xl border border-cyan-200 bg-cyan-50/70 px-4 py-3">
                <div className="text-sm font-semibold text-cyan-900">Magic Link Detected</div>
                <p className="mt-1 text-xs text-cyan-700">
                  Continue directly with your secure link.
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  onClick={handleMagicLinkSubmit}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Signing in..." : "Use Magic Link"}
                </Button>
              </div>
            ) : null}

            <form className="grid gap-3" onSubmit={handleCodeSubmit}>
              <label className="grid gap-1.5 text-sm text-slate-600">
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Access Code
                </span>
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="6-digit code"
                  maxLength={12}
                  required
                />
              </label>

              <label className="grid gap-1.5 text-sm text-slate-600">
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Patient ID (preferred)
                </span>
                <Input
                  value={patientId}
                  onChange={(event) => setPatientId(event.target.value)}
                  placeholder="Patient UUID"
                />
              </label>

              <label className="grid gap-1.5 text-sm text-slate-600">
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  Email (optional fallback)
                </span>
                <Input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="patient@example.com"
                />
              </label>

              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Signing in..." : "Sign in with Code"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="border-slate-200/70 bg-slate-50/70 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg text-slate-900">Portal Scope</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600">
            <p>Only assigned forms are shown here.</p>
            <p>Clinical notes are never displayed in the patient portal.</p>
            <p>Forms are grouped by service so you can complete the right paperwork.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

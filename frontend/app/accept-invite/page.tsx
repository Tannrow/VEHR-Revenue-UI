"use client";

import Link from "next/link";
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

type InvitePreviewResponse = {
  email: string;
  allowed_roles: string[];
  expires_at: string;
  status: string;
};

function roleLabel(value: string): string {
  return value
    .split("_")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export default function AcceptInvitePage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [inviteEmail, setInviteEmail] = useState<string | null>(null);
  const [roleOptions, setRoleOptions] = useState<string[]>([]);

  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token")?.trim() || "");
  }, []);

  useEffect(() => {
    let isMounted = true;
    if (!token) return;

    async function loadInvitePreview() {
      try {
        const preview = await apiFetch<InvitePreviewResponse>(
          `/api/v1/auth/invites/preview?token=${encodeURIComponent(token)}`,
          { cache: "no-store" },
        );
        if (!isMounted) return;
        const options = preview.allowed_roles ?? [];
        setInviteEmail(preview.email);
        setRoleOptions(options);
        if (options[0]) {
          setRole(options[0]);
        }
      } catch (loadError) {
        if (!isMounted) return;
        if (loadError instanceof ApiError || loadError instanceof Error) {
          setError(loadError.message || "Unable to load invite.");
        } else {
          setError("Unable to load invite.");
        }
      }
    }

    void loadInvitePreview();
    return () => {
      isMounted = false;
    };
  }, [token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("Missing invite token. Open the invite link from your email.");
      return;
    }
    if (!password.trim()) {
      setError("Password is required.");
      return;
    }
    if (!role) {
      setError("Role is required.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      setSubmitting(true);
      const response = await apiFetch<TokenResponse>("/api/v1/auth/accept-invite", {
        method: "POST",
        body: JSON.stringify({
          token,
          role,
          full_name: fullName.trim() || null,
          password,
        }),
      });
      persistAccessToken(response.access_token);
      router.replace("/dashboard");
    } catch (submitError) {
      if (submitError instanceof ApiError || submitError instanceof Error) {
        setError(submitError.message || "Failed to accept invite.");
      } else {
        setError("Failed to accept invite.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen px-6 py-16 sm:px-10">
      <div className="mx-auto grid w-full max-w-5xl gap-6 lg:grid-cols-[1.15fr_1fr]">
        <Card className="border-slate-200/70 bg-white/95 shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
          <CardHeader className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">Invite</p>
            <CardTitle className="text-3xl tracking-tight text-slate-900">Join {BRANDING.name}</CardTitle>
            <p className="text-sm text-slate-500">
              Set your profile and password to activate your account.
            </p>
            {inviteEmail ? (
              <p className="text-sm text-slate-500">Invited email: {inviteEmail}</p>
            ) : null}
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              {error ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {error}
                </div>
              ) : null}

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="full_name">
                  Full name
                </label>
                <Input
                  id="full_name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Your full name"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="role">
                  Role
                </label>
                <select
                  id="role"
                  className="h-9 w-full rounded-md border border-slate-200 px-3 text-sm"
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                  disabled={roleOptions.length === 0}
                >
                  {roleOptions.map((roleOption) => (
                    <option key={roleOption} value={roleOption}>
                      {roleLabel(roleOption)}
                    </option>
                  ))}
                </select>
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
                  autoComplete="new-password"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" htmlFor="confirm_password">
                  Confirm password
                </label>
                <Input
                  id="confirm_password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>

              <Button type="submit" className="h-10 w-full rounded-full" disabled={submitting}>
                {submitting ? "Activating account..." : "Accept Invite"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="border-slate-200/70 bg-slate-50/70 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg text-slate-900">Access Help</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600">
            <p>If this link is expired, ask an admin to resend your invite.</p>
            <p>
              After acceptance, you will be signed in and redirected to your dashboard.
            </p>
            <p>
              Already have an account? <Link href="/login" className="text-slate-900 underline">Sign in</Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

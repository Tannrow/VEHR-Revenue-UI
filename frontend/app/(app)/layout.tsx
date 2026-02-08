"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import Sidebar from "../components/sidebar";
import { BRANDING } from "@/lib/branding";
import { ApiError, apiFetch } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

function buildLoginPath(pathname: string | null): string {
  const next = pathname && pathname.startsWith("/") ? pathname : "/dashboard";
  return `/login?next=${encodeURIComponent(next)}`;
}

function initialsForUser(user: MeResponse | null): string {
  if (!user) return "VE";
  const source = user.full_name?.trim() || user.email;
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  useEffect(() => {
    if (currentUser) {
      return;
    }

    let isMounted = true;

    async function validateSession() {
      setIsCheckingSession(true);
      setSessionError(null);
      try {
        const me = await apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" });
        if (!isMounted) return;
        setCurrentUser(me);
      } catch (error) {
        if (!isMounted) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          clearAccessToken();
          router.replace(buildLoginPath(pathname));
          return;
        }
        setSessionError(error instanceof Error ? error.message : "Failed to validate session");
      } finally {
        if (isMounted) {
          setIsCheckingSession(false);
        }
      }
    }

    validateSession();
    return () => {
      isMounted = false;
    };
  }, [currentUser, pathname, router]);

  const userInitials = useMemo(() => initialsForUser(currentUser), [currentUser]);

  function handleSignOut() {
    clearAccessToken();
    router.replace("/login");
  }

  if (isCheckingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
          Verifying session...
        </div>
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
        <div className="max-w-xl rounded-xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
          {sessionError}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] flex-col gap-6 px-4 py-6 lg:flex-row lg:items-stretch lg:gap-8 lg:px-6">
        <Sidebar role={currentUser?.role} />
        <div className="flex min-h-[calc(100vh-3rem)] flex-1 flex-col overflow-hidden rounded-3xl border border-slate-200/70 bg-white/95 shadow-[0_30px_80px_rgba(15,23,42,0.08)] backdrop-blur">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70 px-6 py-4">
            <div className="space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-500">
                {BRANDING.name}
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {BRANDING.tagline}
              </div>
            </div>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
              <div className="relative w-full sm:w-72">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.8}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-4 w-4"
                  >
                    <circle cx="11" cy="11" r="7" />
                    <path d="M20 20l-3.5-3.5" />
                  </svg>
                </span>
                <input
                  className="h-10 w-full rounded-full border border-slate-200 bg-white pl-10 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  placeholder="Search patients, encounters, tasks"
                  type="search"
                />
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-3 rounded-full border border-slate-200 bg-white px-3 py-2 text-left">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
                    {userInitials}
                  </span>
                  <span className="hidden sm:block">
                    <span className="block text-xs font-semibold text-slate-900">
                      {currentUser?.full_name || currentUser?.email || "Session User"}
                    </span>
                    <span className="block text-[11px] text-slate-500">
                      {currentUser?.role || "member"}
                    </span>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="h-10 rounded-full border border-slate-200 bg-white px-4 text-xs font-semibold uppercase tracking-[0.2em] text-slate-600 transition hover:border-slate-300"
                >
                  Sign Out
                </button>
              </div>
            </div>
          </header>
          <main className="flex-1 px-6 py-6 sm:px-8 sm:py-8">{children}</main>
          <footer className="border-t border-slate-200/70 px-6 py-3 text-xs text-slate-500">
            {BRANDING.internalNote}
          </footer>
        </div>
      </div>
    </div>
  );
}

"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import CopilotDrawer from "../components/copilot-drawer";
import { BRANDING } from "@/lib/branding";
import { ApiError, apiFetch } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import {
  ModuleId,
  getModuleById,
  pageTitleForPath,
  resolveModuleForPath,
  visibleModuleNavItems,
} from "@/lib/modules";
import { MePreferences, fetchMePreferences, patchMePreferences } from "@/lib/preferences";

type MeResponse = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  organization_id: string;
};

function buildLoginPath(pathname: string | null): string {
  const next = pathname && pathname.startsWith("/") ? pathname : "/directory";
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

function NavGlyph({ label }: { label: string }) {
  return (
    <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-slate-200 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-700">
      {label.slice(0, 2)}
    </span>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [preferences, setPreferences] = useState<MePreferences | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [viewportWidth, setViewportWidth] = useState(1440);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const lastPatchedModuleRef = useRef<ModuleId | null>(null);

  useEffect(() => {
    function onResize() {
      setViewportWidth(window.innerWidth);
    }

    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function validateSessionAndPrefs() {
      setIsCheckingSession(true);
      setSessionError(null);
      try {
        const [me, prefs] = await Promise.all([
          apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
          fetchMePreferences(),
        ]);
        if (!isMounted) return;
        setCurrentUser(me);
        setPreferences(prefs);
      } catch (error) {
        if (!isMounted) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          clearAccessToken();
          const query = typeof window !== "undefined" ? window.location.search : "";
          if (pathname === "/directory" && !query) {
            router.replace("/login");
            return;
          }
          const nextPath = pathname ? `${pathname}${query}` : "/directory";
          router.replace(buildLoginPath(nextPath));
          return;
        }
        setSessionError(error instanceof Error ? error.message : "Failed to validate session");
      } finally {
        if (isMounted) {
          setIsCheckingSession(false);
        }
      }
    }

    validateSessionAndPrefs();
    return () => {
      isMounted = false;
    };
  }, [pathname, router]);

  const isDirectory = pathname === "/directory";
  const activeModuleId = resolveModuleForPath(pathname);
  const activeModule = activeModuleId ? getModuleById(activeModuleId) : null;

  const grantedPermissions = useMemo(
    () => new Set(preferences?.granted_permissions ?? []),
    [preferences?.granted_permissions],
  );

  const moduleNavItems = useMemo(() => {
    if (!activeModuleId) return [];
    return visibleModuleNavItems(activeModuleId, grantedPermissions);
  }, [activeModuleId, grantedPermissions]);

  const userInitials = useMemo(() => initialsForUser(currentUser), [currentUser]);

  const isMobile = viewportWidth < 1024;
  const isForcedCollapsed = viewportWidth < 1280;
  const isSidebarCollapsed = isForcedCollapsed || Boolean(preferences?.sidebar_collapsed);
  const isCallCenterTheme = activeModuleId === "call_center";

  useEffect(() => {
    if (!preferences || !activeModuleId || isDirectory) {
      return;
    }
    if (!preferences.allowed_modules.includes(activeModuleId)) {
      router.replace("/directory");
      return;
    }

    if (preferences.last_active_module === activeModuleId) {
      lastPatchedModuleRef.current = activeModuleId;
      return;
    }

    if (lastPatchedModuleRef.current === activeModuleId) {
      return;
    }

    lastPatchedModuleRef.current = activeModuleId;
    patchMePreferences({ last_active_module: activeModuleId })
      .then((updated) => {
        setPreferences(updated);
      })
      .catch(() => {
        lastPatchedModuleRef.current = null;
      });
  }, [activeModuleId, isDirectory, preferences, router]);

  useEffect(() => {
    if (!isMobile) {
      setMobileSidebarOpen(false);
    }
  }, [isMobile]);

  async function updatePreferences(partial: Partial<MePreferences>) {
    try {
      const payload: {
        last_active_module?: ModuleId | null;
        sidebar_collapsed?: boolean;
        copilot_enabled?: boolean;
      } = {};
      if (Object.prototype.hasOwnProperty.call(partial, "last_active_module")) {
        payload.last_active_module = partial.last_active_module ?? null;
      }
      if (Object.prototype.hasOwnProperty.call(partial, "sidebar_collapsed")) {
        payload.sidebar_collapsed = Boolean(partial.sidebar_collapsed);
      }
      if (Object.prototype.hasOwnProperty.call(partial, "copilot_enabled")) {
        payload.copilot_enabled = Boolean(partial.copilot_enabled);
      }

      const updated = await patchMePreferences(payload);
      setPreferences(updated);
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Failed to save preferences");
    }
  }

  function handleSignOut() {
    clearAccessToken();
    router.replace("/login");
  }

  if (isCheckingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--ui-gray-canvas)] px-6">
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600 shadow-sm">
          Verifying session...
        </div>
      </div>
    );
  }

  if (sessionError || !preferences) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--ui-gray-canvas)] px-6">
        <div className="max-w-xl rounded-xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 shadow-sm">
          {sessionError || "Unable to load workspace preferences"}
        </div>
      </div>
    );
  }

  const topTitle = isDirectory
    ? "Organizational Directory"
    : activeModule
      ? `${activeModule.name} / ${pageTitleForPath(pathname, activeModule.id)}`
      : "Workspace";

  const showSidebar = !isDirectory && !!activeModule;

  return (
    <div className={`min-h-screen ${isCallCenterTheme ? "bg-slate-100" : "bg-[var(--ui-gray-canvas)]"}`}>
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] gap-4 px-3 py-4 sm:px-4 lg:gap-5 lg:px-6">
        {showSidebar && !isMobile ? (
          <aside
            className={`sticky top-4 h-[calc(100vh-2rem)] shrink-0 overflow-hidden rounded-xl border border-slate-900 bg-[var(--ui-nav-bg)] text-slate-200 transition-all duration-200 ${
              isSidebarCollapsed ? "w-20" : "w-72"
            }`}
          >
            <div className="flex h-full flex-col">
              <div className="border-b border-slate-800 px-4 py-4">
                <div className={`text-sm font-semibold tracking-tight text-white ${isSidebarCollapsed ? "text-center" : ""}`}>
                  {isSidebarCollapsed ? "E360" : activeModule?.name}
                </div>
                {!isSidebarCollapsed ? (
                  <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Module Navigation
                  </div>
                ) : null}
              </div>

              <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2" aria-label="Module navigation">
                {moduleNavItems.map((item) => {
                  const isInternal = item.href.startsWith("/");
                  const isActive = isInternal && (pathname === item.href || pathname?.startsWith(`${item.href}/`));
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      target={item.external ? "_blank" : undefined}
                      rel={item.external ? "noopener noreferrer" : undefined}
                      className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                        isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      <NavGlyph label={item.label} />
                      {!isSidebarCollapsed ? <span className="text-sm font-semibold">{item.label}</span> : null}
                    </Link>
                  );
                })}
              </nav>

              <div className="border-t border-slate-800 p-2">
                {viewportWidth >= 1280 ? (
                  <button
                    type="button"
                    onClick={() => updatePreferences({ sidebar_collapsed: !preferences.sidebar_collapsed })}
                    className="flex w-full items-center justify-center rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  >
                    {preferences.sidebar_collapsed ? "Expand" : "Collapse"}
                  </button>
                ) : (
                  <div className="rounded-lg border border-slate-700 px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                    Auto-collapsed
                  </div>
                )}
              </div>
            </div>
          </aside>
        ) : null}

        <div className="flex min-h-[calc(100vh-2rem)] min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-200 px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                  {BRANDING.name}
                </div>
                <div className="truncate text-lg font-semibold tracking-tight text-slate-900">{topTitle}</div>
              </div>

              <div className="flex items-center gap-2">
                {showSidebar && isMobile ? (
                  <button
                    type="button"
                    onClick={() => setMobileSidebarOpen(true)}
                    className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition-colors hover:border-slate-300"
                  >
                    Module Menu
                  </button>
                ) : null}

                <Link
                  href="/directory"
                  className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition-colors hover:border-slate-300"
                >
                  Launcher
                </Link>

                <button
                  type="button"
                  onClick={() => updatePreferences({ copilot_enabled: !preferences.copilot_enabled })}
                  className={`inline-flex h-9 items-center rounded-lg border px-3 text-xs font-semibold uppercase tracking-[0.14em] transition-colors ${
                    preferences.copilot_enabled
                      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                      : "border-slate-300 bg-slate-100 text-slate-700"
                  }`}
                >
                  Tanner {preferences.copilot_enabled ? "On" : "Off"}
                </button>

                <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left">
                  <span className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-900 text-[11px] font-semibold text-white">
                    {userInitials}
                  </span>
                  <span className="hidden sm:block">
                    <span className="block text-xs font-semibold text-slate-900">
                      {currentUser?.full_name || currentUser?.email || "Session User"}
                    </span>
                    <span className="block text-[11px] text-slate-500">{currentUser?.role || "member"}</span>
                  </span>
                  <button
                    type="button"
                    onClick={handleSignOut}
                    className="rounded-md px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
                  >
                    Sign Out
                  </button>
                </div>
              </div>
            </div>
          </header>

          <main className={`flex-1 overflow-auto ${isCallCenterTheme ? "px-4 py-4" : "px-5 py-5 sm:px-6 sm:py-6"}`}>
            {children}
          </main>

          <footer className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500">{BRANDING.internalNote}</footer>
        </div>
      </div>

      {showSidebar && isMobile ? (
        <>
          <button
            type="button"
            aria-label="Close module sidebar"
            onClick={() => setMobileSidebarOpen(false)}
            className={`fixed inset-0 z-40 bg-slate-900/40 transition-opacity ${mobileSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}
          />
          <aside
            className={`fixed left-0 top-0 z-50 h-full w-[82vw] max-w-[320px] border-r border-slate-800 bg-[var(--ui-nav-bg)] p-3 text-slate-200 shadow-xl transition-transform duration-200 ${
              mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-semibold text-white">{activeModule?.name}</div>
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(false)}
                className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300"
              >
                Close
              </button>
            </div>
            <nav className="space-y-1">
              {moduleNavItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  target={item.external ? "_blank" : undefined}
                  rel={item.external ? "noopener noreferrer" : undefined}
                  onClick={() => setMobileSidebarOpen(false)}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors ${
                    pathname === item.href || pathname?.startsWith(`${item.href}/`)
                      ? "bg-white/10 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <NavGlyph label={item.label} />
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>
          </aside>
        </>
      ) : null}

      {preferences.copilot_enabled ? <CopilotDrawer /> : null}
    </div>
  );
}

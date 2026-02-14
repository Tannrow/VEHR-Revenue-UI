"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import CopilotDrawer from "../components/copilot-drawer";
import { ModuleSidebar } from "@/components/app-shell/module-sidebar";
import { TopBar } from "@/components/app-shell/top-bar";
import { Button } from "@/components/ui/button";
import { BRANDING } from "@/lib/branding";
import { ApiError, apiFetch } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { AppLayoutConfigContext, type AppLayoutConfig } from "@/lib/app-layout-config";
import {
  ModuleId,
  getModuleById,
  listModules,
  pageTitleForPath,
  resolveModuleForPath,
  visibleModuleNavItems,
} from "@/lib/modules";
import { MePreferences, fetchMePreferences, patchMePreferences } from "@/lib/preferences";
import { type SidebarNavGroup } from "@/components/enterprise/sidebar-nav";

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

function displayRoleLabel(role: string | undefined): string {
  if (!role) return "Member";
  return role
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

type EnterpriseNavSection = "Clinical" | "Revenue" | "Operations" | "Compliance" | "System";

const ENTERPRISE_SECTION_ORDER: EnterpriseNavSection[] = [
  "Clinical",
  "Revenue",
  "Operations",
  "Compliance",
  "System",
];

function sectionForNavItem(href: string, label: string): EnterpriseNavSection {
  const normalizedHref = href.toLowerCase();
  const normalizedLabel = label.toLowerCase();

  if (
    normalizedHref.startsWith("/clients")
    || normalizedHref.startsWith("/forms")
    || normalizedHref.startsWith("/documents")
    || normalizedHref.startsWith("/patients")
    || normalizedHref.startsWith("/encounters")
  ) {
    return "Clinical";
  }

  if (
    normalizedHref.startsWith("/billing")
    || normalizedLabel.includes("billing")
    || normalizedLabel.includes("claim")
    || normalizedLabel.includes("remittance")
    || normalizedLabel.includes("revenue")
  ) {
    return "Revenue";
  }

  if (normalizedHref.startsWith("/audit-center") || normalizedHref.startsWith("/compliance")) {
    return "Compliance";
  }

  if (
    normalizedHref.startsWith("/admin")
    || normalizedHref.startsWith("/organization")
    || normalizedHref.startsWith("/integrations")
    || normalizedHref.startsWith("/sharepoint")
    || normalizedLabel.includes("admin")
    || normalizedLabel.includes("integration")
    || normalizedLabel.includes("organization")
  ) {
    return "System";
  }

  return "Operations";
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
  const [layoutConfig, setLayoutConfigState] = useState<Partial<AppLayoutConfig>>({});
  const [searchQuery, setSearchQuery] = useState("");

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

    void validateSessionAndPrefs();
    return () => {
      isMounted = false;
    };
  }, [pathname, router]);

  const isDirectory = pathname === "/directory";
  const activeModuleId = resolveModuleForPath(pathname);
  const activeModule = activeModuleId ? getModuleById(activeModuleId) : null;
  const isMobile = viewportWidth < 1024;

  const grantedPermissions = useMemo(
    () => new Set(preferences?.granted_permissions ?? []),
    [preferences?.granted_permissions],
  );

  const allowedModuleSet = useMemo(
    () => new Set(preferences?.allowed_modules ?? []),
    [preferences?.allowed_modules],
  );

  const userInitials = useMemo(() => initialsForUser(currentUser), [currentUser]);

  const moduleSidebarGroups = useMemo<SidebarNavGroup[]>(() => {
    const buckets = new Map<EnterpriseNavSection, SidebarNavGroup["items"]>();
    for (const section of ENTERPRISE_SECTION_ORDER) {
      buckets.set(section, []);
    }

    const seenLinks = new Set<string>();
    for (const moduleDef of listModules()) {
      if (!allowedModuleSet.has(moduleDef.id)) {
        continue;
      }
      const visibleItems = visibleModuleNavItems(moduleDef.id, grantedPermissions);
      for (const item of visibleItems) {
        if (seenLinks.has(item.href)) {
          continue;
        }
        seenLinks.add(item.href);

        const section = sectionForNavItem(item.href, item.label);
        const isInternal = item.href.startsWith("/");
        const isActive = isInternal && (pathname === item.href || pathname?.startsWith(`${item.href}/`));

        buckets.get(section)?.push({
          id: `${moduleDef.id}-${item.href}`,
          label: item.label,
          href: item.href,
          external: item.external,
          active: isActive,
          description: item.external ? "Opens in a new tab" : undefined,
          testId: `module-nav-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
        });
      }
    }

    return ENTERPRISE_SECTION_ORDER.map((section) => ({
      id: section.toLowerCase(),
      label: section,
      items: buckets.get(section) ?? [],
    })).filter((group) => group.items.length > 0);
  }, [allowedModuleSet, grantedPermissions, pathname]);

  const showSidebarByDefault = !isDirectory && !!activeModule;
  const showSidebar = typeof layoutConfig.showSidebar === "boolean"
    ? layoutConfig.showSidebar
    : showSidebarByDefault;
  const isSidebarCollapsed = !isMobile && Boolean(preferences?.sidebar_collapsed);

  const topTitle = layoutConfig.pageTitle
    ?? (isDirectory
      ? "Organizational Directory"
      : activeModule
        ? `${activeModule.name} / ${pageTitleForPath(pathname, activeModule.id)}`
        : "Workspace");

  const subtitle = layoutConfig.subtitle
    ?? (isDirectory
      ? "Launch a module workspace and continue where your team left off."
      : activeModule?.description);

  const showSearch = layoutConfig.showSearch ?? false;
  const searchPlaceholder = layoutConfig.searchPlaceholder ?? "Search workspace";

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

  const setLayoutConfig = useCallback((config: Partial<AppLayoutConfig>) => {
    setLayoutConfigState((current) => ({ ...current, ...config }));
  }, []);

  const resetLayoutConfig = useCallback(() => {
    setLayoutConfigState({});
  }, []);

  useEffect(() => {
    resetLayoutConfig();
    setSearchQuery("");
  }, [pathname, resetLayoutConfig]);

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
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="ui-panel px-5 py-4 text-sm text-[var(--neutral-muted)]">
          Verifying session...
        </div>
      </div>
    );
  }

  if (sessionError || !preferences) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="max-w-xl rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-5 py-4 text-sm text-[var(--danger)] shadow-sm">
          {sessionError || "Unable to load workspace preferences"}
        </div>
      </div>
    );
  }

  const layoutContextValue = {
    setLayoutConfig,
    resetLayoutConfig,
    searchQuery,
    setSearchQuery,
  };

  const utilitySlot = (
    <>
      <Button variant="outline" size="sm" asChild>
        <Link href="/directory">Launcher</Link>
      </Button>

      <Button
        type="button"
        variant={preferences.copilot_enabled ? "secondary" : "outline"}
        size="sm"
        onClick={() => updatePreferences({ copilot_enabled: !preferences.copilot_enabled })}
      >
        Tanner {preferences.copilot_enabled ? "On" : "Off"}
      </Button>

      <div className="inline-flex items-center gap-[var(--space-8)] rounded-xl border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-8)] py-[var(--space-8)]">
        <span className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-6)] bg-[var(--primary)] text-[11px] font-semibold text-[var(--primary-foreground)]">
          {userInitials}
        </span>
        <span className="hidden sm:block">
          <span className="block text-xs font-semibold text-[var(--neutral-text)]">
            {currentUser?.full_name || currentUser?.email || "Session User"}
          </span>
          <span className="block text-[11px] text-[var(--neutral-muted)]">
            {displayRoleLabel(currentUser?.role)}
          </span>
        </span>
        <button
          type="button"
          onClick={handleSignOut}
          className="rounded-[var(--radius-4)] px-[var(--space-8)] py-[var(--space-4)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--neutral-muted)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--neutral-text)]"
        >
          Sign Out
        </button>
      </div>
    </>
  );

  return (
    <AppLayoutConfigContext.Provider value={layoutContextValue}>
      <div className="min-h-screen bg-background text-foreground antialiased">
        <div className="mx-auto flex min-h-screen w-full max-w-7xl gap-[var(--space-16)] px-6 py-6">
          {showSidebar && !isMobile ? (
            <aside
              className={`hidden shrink-0 transition-[width] duration-200 lg:block ${isSidebarCollapsed ? "w-20" : "w-72"}`}
            >
              <ModuleSidebar
                moduleName={activeModule?.name ?? "Module"}
                groups={moduleSidebarGroups}
                collapsed={isSidebarCollapsed}
                showCollapseToggle={true}
                onToggleCollapsed={() =>
                  updatePreferences({ sidebar_collapsed: !preferences.sidebar_collapsed })}
              />
            </aside>
          ) : null}

          <div className="flex min-w-0 flex-1 flex-col gap-[var(--space-16)]">
            <TopBar
              productName={BRANDING.name}
              pageTitle={topTitle}
              subtitle={subtitle}
              showSearch={showSearch}
              searchPlaceholder={searchPlaceholder}
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              actions={layoutConfig.actions}
              utilitySlot={utilitySlot}
              showMobileSidebarButton={showSidebar}
              onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
            />

            <main className="ui-panel min-h-0 flex-1 overflow-auto p-[var(--space-24)]">
              {children}
            </main>

            <footer className="px-1 text-xs text-[var(--neutral-muted)]">{BRANDING.internalNote}</footer>
          </div>
        </div>

        {showSidebar && isMobile ? (
          <>
            <button
              type="button"
              aria-label="Close module sidebar"
              onClick={() => setMobileSidebarOpen(false)}
              className={`fixed inset-0 z-40 bg-black/35 transition-opacity ${mobileSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}
            />
            <aside
              className={`fixed left-0 top-0 z-50 h-full w-[86vw] max-w-[360px] bg-background p-[var(--space-16)] shadow-[var(--shadow-lg)] transition-transform duration-200 ${mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
            >
              <div className="mb-[var(--space-12)] flex items-center justify-between">
                <p className="ui-type-section-title text-[var(--neutral-text)]">{activeModule?.name ?? "Module"}</p>
                <Button type="button" variant="outline" size="sm" onClick={() => setMobileSidebarOpen(false)}>
                  Close
                </Button>
              </div>
              <ModuleSidebar moduleName={activeModule?.name ?? "Module"} groups={moduleSidebarGroups} />
            </aside>
          </>
        ) : null}

        {preferences.copilot_enabled ? <CopilotDrawer /> : null}
      </div>
    </AppLayoutConfigContext.Provider>
  );
}

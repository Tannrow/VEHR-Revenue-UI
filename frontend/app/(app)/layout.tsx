"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Bell, Brain } from "lucide-react";

import CopilotDrawer from "../components/copilot-drawer";
import { ModuleSidebar } from "@/components/app-shell/module-sidebar";
import { TopBar } from "@/components/app-shell/top-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BRANDING } from "@/lib/branding";
import { ApiError, apiFetch } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { AppLayoutConfigContext, type AppLayoutConfig } from "@/lib/app-layout-config";
import {
  defaultRouteForModule,
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

function isTransientNetworkError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status >= 500;
  }
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    return message.includes("failed to fetch")
      || message.includes("networkerror")
      || message.includes("load failed");
  }
  return false;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function runWithTransientRetry<T>(operation: () => Promise<T>, maxAttempts = 2): Promise<T> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (!isTransientNetworkError(error) || attempt === maxAttempts) {
        throw error;
      }
      await delay(250 * attempt);
    }
  }
  throw lastError;
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
        const [me, prefs] = await runWithTransientRetry(
          () =>
            Promise.all([
              apiFetch<MeResponse>("/api/v1/auth/me", { cache: "no-store" }),
              fetchMePreferences(),
            ]),
          2,
        );
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
  const isSharePointCategoryActive = pathname === "/sharepoint"
    || pathname?.startsWith("/sharepoint/")
    || pathname === "/organization/home"
    || pathname?.startsWith("/organization/home/");
  const activeMainCategoryId: ModuleId | "sharepoint" | null = isSharePointCategoryActive
    ? "sharepoint"
    : activeModuleId;
  const isMobile = viewportWidth < 1024;

  const grantedPermissionsList = useMemo(
    () => (Array.isArray(preferences?.granted_permissions) ? preferences.granted_permissions : []),
    [preferences?.granted_permissions],
  );
  const allowedModuleIds = useMemo(
    () => (Array.isArray(preferences?.allowed_modules) ? preferences.allowed_modules : []),
    [preferences?.allowed_modules],
  );

  const grantedPermissions = useMemo(
    () => new Set(grantedPermissionsList),
    [grantedPermissionsList],
  );

  const allowedModuleSet = useMemo(
    () => new Set(allowedModuleIds),
    [allowedModuleIds],
  );
  const allowedModules = useMemo(
    () => listModules().filter((moduleDef) => allowedModuleSet.has(moduleDef.id)),
    [allowedModuleSet],
  );

  const userInitials = useMemo(() => initialsForUser(currentUser), [currentUser]);

  const moduleSidebarGroups = useMemo<SidebarNavGroup[]>(() => {
    const mainCategoryItems = allowedModules.map((moduleDef) => ({
      id: `module-${moduleDef.id}`,
      label: moduleDef.name,
      href: defaultRouteForModule(moduleDef.id),
      active: moduleDef.id === activeMainCategoryId,
      testId: `module-main-${moduleDef.id.replace(/_/g, "-")}`,
    }));

    if (allowedModuleSet.has("administration")) {
      mainCategoryItems.push({
        id: "module-sharepoint",
        label: "SharePoint",
        href: "/sharepoint",
        active: isSharePointCategoryActive,
        testId: "module-main-sharepoint",
      });
    }

    const subcategoryItems = activeMainCategoryId && activeMainCategoryId !== "sharepoint"
      ? visibleModuleNavItems(activeMainCategoryId, grantedPermissions).map((item) => {
      const isInternal = item.href.startsWith("/");
      const isActive = isInternal && (pathname === item.href || pathname?.startsWith(`${item.href}/`));
      return {
        id: `${activeMainCategoryId}-${item.href}`,
        label: item.label,
        href: item.href,
        external: item.external,
        active: isActive,
        description: item.external ? "Opens in a new tab" : undefined,
        testId: `module-nav-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      };
    })
      : [];

    const groups: SidebarNavGroup[] = [];
    if (mainCategoryItems.length > 0) {
      groups.push({
        id: "main-categories",
        label: "Main categories",
        items: mainCategoryItems,
      });
    }
    if (subcategoryItems.length > 0) {
      groups.push({
        id: "subcategories",
        label: "Subcategories",
        items: subcategoryItems,
      });
    }
    return groups;
  }, [activeMainCategoryId, allowedModuleSet, allowedModules, grantedPermissions, isSharePointCategoryActive, pathname]);

  const showSidebarByDefault = !isDirectory && !!activeModule;
  const showSidebar = typeof layoutConfig.showSidebar === "boolean"
    ? layoutConfig.showSidebar
    : showSidebarByDefault;
  const isSidebarCollapsed = !isMobile && Boolean(preferences?.sidebar_collapsed);

  const topModuleLabel = layoutConfig.moduleLabel
    ?? (isDirectory ? "Home" : isSharePointCategoryActive ? "SharePoint" : activeModule?.name ?? "Workspace");

  const topTitle = layoutConfig.pageTitle
    ?? (isDirectory
      ? "Organizational Directory"
      : activeModule
        ? pageTitleForPath(pathname, activeModule.id)
        : "Workspace");

  const subtitle = layoutConfig.subtitle
    ?? (isDirectory
      ? "Launch a module workspace and continue where your team left off."
      : activeModule?.description);

  const showSearch = layoutConfig.showSearch ?? false;
  const searchPlaceholder = layoutConfig.searchPlaceholder ?? "Search workspace";
  const notificationCount = layoutConfig.notificationCount ?? 0;

  useEffect(() => {
    if (!preferences || !activeModuleId || isDirectory) {
      return;
    }
    if (!allowedModuleIds.includes(activeModuleId)) {
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
  }, [activeModuleId, allowedModuleIds, isDirectory, preferences, router]);

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

  async function handleOpenTanner() {
    if (!preferences?.copilot_enabled) {
      await updatePreferences({ copilot_enabled: true });
    }
    const trigger = document.querySelector<HTMLButtonElement>("[data-testid='copilot-trigger']");
    trigger?.click();
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
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="relative"
        aria-label="Notifications"
        onClick={() => router.push("/activity-log")}
      >
        <Bell className="h-4 w-4" />
        <span className="sr-only">Notifications</span>
        {notificationCount > 0 ? (
          <span className="absolute -right-1 -top-1 inline-flex min-w-[18px] justify-center rounded-[var(--radius-4)] bg-[var(--status-critical)] px-1 text-[10px] font-semibold text-white">
            {notificationCount > 99 ? "99+" : notificationCount}
          </span>
        ) : null}
      </Button>

      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => {
          void handleOpenTanner();
        }}
      >
        <Brain className="h-4 w-4" />
        Tanner AI
      </Button>

      <div className="inline-flex items-center gap-[var(--space-8)] rounded-xl border border-[var(--neutral-border)] bg-[var(--neutral-panel)] px-[var(--space-8)] py-[6px]">
        <span className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-6)] bg-[var(--primary)] text-[11px] font-semibold text-[var(--primary-foreground)]">
          {userInitials}
        </span>
        <span className="hidden xl:block">
          <span className="block text-xs font-semibold leading-tight text-[var(--neutral-text)]">
            {currentUser?.full_name || currentUser?.email || "Session User"}
          </span>
          <Badge variant="outline" className="mt-[2px] text-[10px]">
            {displayRoleLabel(currentUser?.role)}
          </Badge>
        </span>
        <Button
          type="button"
          variant={preferences.copilot_enabled ? "secondary" : "outline"}
          size="sm"
          onClick={() => updatePreferences({ copilot_enabled: !preferences.copilot_enabled })}
        >
          Tanner {preferences.copilot_enabled ? "On" : "Off"}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={handleSignOut}>
          Sign Out
        </Button>
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
              productHref="/directory"
              moduleLabel={topModuleLabel}
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
              className={`fixed left-0 top-0 z-50 h-full w-[86vw] max-w-[360px] bg-[linear-gradient(180deg,var(--sidebar-bg)_0%,var(--sidebar-bg-2)_100%)] p-[var(--space-16)] text-[var(--sidebar-text)] shadow-[var(--shadow-lg)] transition-transform duration-200 ${mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
            >
              <div className="mb-[var(--space-12)] flex items-center justify-between">
                <p className="ui-type-section-title text-[var(--sidebar-text)]">{activeModule?.name ?? "Module"}</p>
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

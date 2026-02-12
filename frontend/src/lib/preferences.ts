import { ApiError, apiFetch } from "@/lib/api";
import { ModuleId, defaultRouteForModule, isModuleId, listModules } from "@/lib/modules";

export type MePreferences = {
  last_active_module: ModuleId | null;
  sidebar_collapsed: boolean;
  copilot_enabled: boolean;
  allowed_modules: ModuleId[];
  granted_permissions: string[];
};

export type PatchMePreferencesPayload = {
  last_active_module?: ModuleId | null;
  sidebar_collapsed?: boolean;
  copilot_enabled?: boolean;
};

function buildFallbackPreferences(
  overrides: Partial<Pick<MePreferences, "last_active_module" | "sidebar_collapsed" | "copilot_enabled">> = {},
): MePreferences {
  const allModules = listModules().map((moduleDef) => moduleDef.id);
  const allPermissions = new Set<string>();

  for (const moduleDef of listModules()) {
    for (const item of moduleDef.navItems) {
      for (const permission of item.requiredAnyPermissions ?? []) {
        allPermissions.add(permission);
      }
    }
  }

  return {
    last_active_module: overrides.last_active_module ?? null,
    sidebar_collapsed: overrides.sidebar_collapsed ?? false,
    copilot_enabled: overrides.copilot_enabled ?? true,
    allowed_modules: allModules,
    granted_permissions: Array.from(allPermissions),
  };
}

export async function fetchMePreferences(): Promise<MePreferences> {
  try {
    return await apiFetch<MePreferences>("/api/v1/me/preferences", { cache: "no-store" });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return buildFallbackPreferences();
    }
    throw error;
  }
}

export async function patchMePreferences(payload: PatchMePreferencesPayload): Promise<MePreferences> {
  try {
    return await apiFetch<MePreferences>("/api/v1/me/preferences", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return buildFallbackPreferences({
        last_active_module: Object.prototype.hasOwnProperty.call(payload, "last_active_module")
          ? payload.last_active_module ?? null
          : null,
        sidebar_collapsed: Object.prototype.hasOwnProperty.call(payload, "sidebar_collapsed")
          ? Boolean(payload.sidebar_collapsed)
          : false,
        copilot_enabled: Object.prototype.hasOwnProperty.call(payload, "copilot_enabled")
          ? Boolean(payload.copilot_enabled)
          : true,
      });
    }
    throw error;
  }
}

export function resolvePostLoginRoute(
  preferences: MePreferences,
  requestedNextPath: string | null,
): string {
  if (requestedNextPath && requestedNextPath.startsWith("/") && requestedNextPath !== "/" && requestedNextPath !== "/login") {
    return requestedNextPath;
  }

  if (preferences.last_active_module && preferences.allowed_modules.includes(preferences.last_active_module)) {
    return defaultRouteForModule(preferences.last_active_module);
  }

  const firstAllowed = preferences.allowed_modules.find((moduleId) => isModuleId(moduleId));
  if (firstAllowed) {
    return defaultRouteForModule(firstAllowed);
  }

  return "/directory";
}

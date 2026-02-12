import { apiFetch } from "@/lib/api";
import { ModuleId, defaultRouteForModule, isModuleId } from "@/lib/modules";

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

export async function fetchMePreferences(): Promise<MePreferences> {
  return apiFetch<MePreferences>("/api/v1/me/preferences", { cache: "no-store" });
}

export async function patchMePreferences(payload: PatchMePreferencesPayload): Promise<MePreferences> {
  return apiFetch<MePreferences>("/api/v1/me/preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
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

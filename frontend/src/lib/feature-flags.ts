function parseBoolean(value: string | undefined, fallback: boolean): boolean {
  if (!value) return fallback;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
}

function resolveClientOverride(key: string): boolean | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return parseBoolean(raw, false);
  } catch {
    return null;
  }
}

export function isUiV2ClientProfileEnabled(): boolean {
  const override = resolveClientOverride("ff_ui_v2_client_profile");
  if (override !== null) return override;
  return parseBoolean(process.env.NEXT_PUBLIC_UI_V2_CLIENT_PROFILE, false);
}


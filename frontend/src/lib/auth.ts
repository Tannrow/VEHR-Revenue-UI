const TOKEN_STORAGE_KEYS = ["vehr_access_token", "access_token"] as const;
const TOKEN_COOKIE_KEYS = ["vehr_access_token", "access_token"] as const;
const TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7;

function getTokenFromCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (const cookie of cookies) {
    const [rawKey, ...rawValue] = cookie.trim().split("=");
    const key = rawKey?.trim();
    if (!key) continue;
    if (TOKEN_COOKIE_KEYS.includes(key as (typeof TOKEN_COOKIE_KEYS)[number])) {
      return decodeURIComponent(rawValue.join("="));
    }
  }
  return null;
}

export function getBrowserAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  for (const key of TOKEN_STORAGE_KEYS) {
    const local = window.localStorage.getItem(key);
    if (local) return local;
  }
  for (const key of TOKEN_STORAGE_KEYS) {
    const session = window.sessionStorage.getItem(key);
    if (session) return session;
  }
  return getTokenFromCookie();
}

export function persistAccessToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }

  for (const key of TOKEN_STORAGE_KEYS) {
    window.localStorage.setItem(key, token);
    window.sessionStorage.setItem(key, token);
  }

  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  for (const key of TOKEN_COOKIE_KEYS) {
    document.cookie = `${key}=${encodeURIComponent(token)}; Path=/; Max-Age=${TOKEN_TTL_SECONDS}; SameSite=Lax${secure}`;
  }
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") {
    return;
  }

  for (const key of TOKEN_STORAGE_KEYS) {
    window.localStorage.removeItem(key);
    window.sessionStorage.removeItem(key);
  }

  for (const key of TOKEN_COOKIE_KEYS) {
    document.cookie = `${key}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
}

const TOKEN_STORAGE_KEYS = ["vehr_access_token", "access_token"] as const;
const TOKEN_COOKIE_KEYS = ["vehr_access_token", "access_token"] as const;
const TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7;
const CUTOVER_FRONTEND_HOST_SUFFIX = ".360-encompass.com";
const PUBLIC_COOKIE_DOMAIN_ENV_KEY = "NEXT_PUBLIC_AUTH_COOKIE_DOMAIN";

function getCookieDomainAttribute(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const configuredDomain = process.env[PUBLIC_COOKIE_DOMAIN_ENV_KEY]?.trim();
  if (configuredDomain) {
    return `; Domain=${configuredDomain}`;
  }

  const host = window.location.hostname.toLowerCase();
  if (host === "360-encompass.com" || host.endsWith(CUTOVER_FRONTEND_HOST_SUFFIX)) {
    return "; Domain=.360-encompass.com";
  }

  return "";
}

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
      const encodedValue = rawValue.join("=");
      try {
        return decodeURIComponent(encodedValue);
      } catch {
        // Some environments can set malformed cookie values; fall back to raw.
        return encodedValue;
      }
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

  const secure = window.location.protocol === "https:";
  const sameSite = secure ? "None" : "Lax";
  const secureAttr = secure ? "; Secure" : "";
  const domainAttr = getCookieDomainAttribute();
  for (const key of TOKEN_COOKIE_KEYS) {
    document.cookie = `${key}=${encodeURIComponent(token)}; Path=/; Max-Age=${TOKEN_TTL_SECONDS}; SameSite=${sameSite}${secureAttr}${domainAttr}`;
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

  const domainAttr = getCookieDomainAttribute();
  for (const key of TOKEN_COOKIE_KEYS) {
    document.cookie = `${key}=; Path=/; Max-Age=0; SameSite=Lax${domainAttr}`;
    document.cookie = `${key}=; Path=/; Max-Age=0; SameSite=None; Secure${domainAttr}`;
  }
}

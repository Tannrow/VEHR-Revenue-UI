export const LOGIN_REQUEST_CONTENT_TYPE = "application/json";
export const INVALID_LOGIN_REQUEST_ERROR = "Login request body must include email and password.";

export type LoginCredentials = {
  email: string;
  password: string;
  organization_id?: string;
};

function normalizeEmail(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const email = value.trim();

  return email ? email : null;
}

function normalizePassword(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  return value.length > 0 ? value : null;
}

function normalizeOrganizationId(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const organizationId = value.trim();

  return organizationId ? organizationId : undefined;
}

export function normalizeLoginCredentials(input: {
  email: unknown;
  password: unknown;
  organization_id?: unknown;
}): LoginCredentials | null {
  const email = normalizeEmail(input.email);
  const password = normalizePassword(input.password);
  const organizationId = normalizeOrganizationId(input.organization_id);

  if (!email || !password) {
    return null;
  }

  return {
    email,
    password,
    ...(organizationId ? { organization_id: organizationId } : {}),
  };
}

export function serializeLoginRequestBody(credentials: LoginCredentials): string {
  return JSON.stringify(credentials);
}

export const LOGIN_REQUEST_CONTENT_TYPE = "application/json";

export type LoginCredentials = {
  username: string;
  password: string;
};

function normalizeUsername(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const username = value.trim();

  return username ? username : null;
}

function normalizePassword(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  return value ? value : null;
}

export function normalizeLoginCredentials(input: {
  username: unknown;
  password: unknown;
}): LoginCredentials | null {
  const username = normalizeUsername(input.username);
  const password = normalizePassword(input.password);

  if (!username || !password) {
    return null;
  }

  return {
    username,
    password,
  };
}

export function serializeLoginRequestBody(credentials: LoginCredentials): string {
  return JSON.stringify(credentials);
}

/**
 * Thin client for the auth + game-history API.
 *
 * The JWT returned by any sign-in flow (email, Google, guest) is kept in
 * localStorage and attached as a Bearer header automatically.
 */

const TOKEN_KEY = "chess_auth_token";

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // storage disabled (private mode) - session won't persist
  }
}

export function setToken(token) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore - in-memory session only */
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export class AuthError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "AuthError";
    this.status = status;
  }
}

function messageFrom(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors are arrays of {msg, loc, ...}.
  if (Array.isArray(detail) && detail[0] && detail[0].msg) return detail[0].msg;
  return `Request failed (${status})`;
}

export async function request(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new AuthError("Could not reach the server. Is the backend running?", 0);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    /* empty/non-JSON body */
  }
  if (!response.ok) throw new AuthError(messageFrom(data, response.status), response.status);
  return data;
}

export const authApi = {
  config: () => request("/api/auth/config"),
  register: (payload) => request("/api/auth/register", { method: "POST", body: payload }),
  login: (payload) => request("/api/auth/login", { method: "POST", body: payload }),
  google: (credential) => request("/api/auth/google", { method: "POST", body: { credential } }),
  guest: (payload) => request("/api/auth/guest", { method: "POST", body: payload ?? {} }),
  me: () => request("/api/auth/me"),
  saveGame: (payload) => request("/api/games", { method: "POST", body: payload }),
  listGames: () => request("/api/games"),
  leaderboard: (difficulty) =>
    request(
      difficulty
        ? `/api/leaderboard?difficulty=${encodeURIComponent(difficulty)}`
        : "/api/leaderboard",
    ),
};

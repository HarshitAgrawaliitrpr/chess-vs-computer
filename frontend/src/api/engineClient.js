/**
 * HTTP client for the FastAPI chess engine.
 *
 * In development the Vite dev server proxies `/api` to the backend; in
 * production the nginx sidecar does the same, so no absolute URL is required
 * unless you point at a remote deployment (VITE_API_BASE_URL).
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class EngineError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "EngineError";
    this.status = status;
  }
}

/**
 * Ask the engine to play the side to move in `fen`.
 *
 * @param {{fen: string, difficulty?: string, depth?: number, timeLimitMs?: number, signal?: AbortSignal}} params
 * @returns {Promise<object>} engine search result (move, fen, score, depth, ...)
 */
export async function fetchComputerMove({
  fen,
  difficulty = "medium",
  depth,
  timeLimitMs,
  signal,
} = {}) {
  const payload = { fen, difficulty };
  if (depth != null) payload.depth = depth;
  if (timeLimitMs != null) payload.time_limit_ms = timeLimitMs;

  const response = await fetch(`${API_BASE}/api/engine/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let detail = `Engine request failed (HTTP ${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* body was not JSON - keep the generic message */
    }
    throw new EngineError(detail, response.status);
  }

  return response.json();
}

/** Fetch the available difficulty profiles (label / depth / elo). */
export async function fetchDifficulties() {
  const response = await fetch(`${API_BASE}/api/difficulties`);
  if (!response.ok) throw new EngineError(`Failed to load difficulties (${response.status})`, response.status);
  return response.json();
}
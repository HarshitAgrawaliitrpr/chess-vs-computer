/**
 * Client for the online multiplayer API.
 *
 * Uses the shared `request` from authClient so the JWT in localStorage is
 * attached automatically. Games are polled (serverless has no WebSockets);
 * see useOnlineGame for the polling loop.
 */

import { request } from "./authClient.js";

export const onlineApi = {
  create: () => request("/api/online/games", { method: "POST", body: {} }),
  join: (code) => request("/api/online/games/join", { method: "POST", body: { code } }),
  state: (gameId) => request(`/api/online/games/${gameId}`),
  move: (gameId, move) =>
    request(`/api/online/games/${gameId}/move`, { method: "POST", body: move }),
  resign: (gameId) => request(`/api/online/games/${gameId}/resign`, { method: "POST", body: {} }),
  cancel: (gameId) => request(`/api/online/games/${gameId}/cancel`, { method: "POST", body: {} }),
};

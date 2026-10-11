/**
 * "My games" panel: the signed-in user's saved results, newest first.
 *
 * ChessGame dispatches a `game-saved` window event after storing a finished
 * game; listening for it keeps this list fresh without prop-drilling.
 */

import { useCallback, useEffect, useState } from "react";
import { authApi } from "../api/authClient.js";
import { useAuth } from "../auth/AuthContext.jsx";

const RESULT_LABEL = { win: "Win", loss: "Loss", draw: "Draw" };

export default function GameHistory() {
  const { user } = useAuth();
  const [games, setGames] = useState(null); // null = still loading
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setGames(await authApi.listGames());
      setError("");
    } catch (err) {
      setGames((previous) => previous ?? []);
      setError(err?.message || "Could not load games.");
    }
  }, []);

  useEffect(() => {
    setGames(null);
    refresh();
    const onSaved = () => refresh();
    window.addEventListener("game-saved", onSaved);
    return () => window.removeEventListener("game-saved", onSaved);
  }, [user?.id, refresh]);

  return (
    <section className="history" aria-label="Game history">
      <div className="history__head">
        <h2>My games</h2>
        <button type="button" className="history__refresh" onClick={refresh}>
          Refresh
        </button>
      </div>

      {error && <p className="history__error">{error}</p>}

      {games === null ? (
        <p className="history__empty">Loading games…</p>
      ) : games.length === 0 ? (
        <p className="history__empty">No saved games yet — finish a match and it will appear here.</p>
      ) : (
        <ul className="history__list">
          {games.map((game) => (
            <li key={game.id} className={`history__row history__row--${game.result}`}>
              <span className={`history__badge history__badge--${game.result}`}>
                {RESULT_LABEL[game.result] ?? game.result}
              </span>
              <span className="history__meta">
                {game.player_color === "w" ? "White" : "Black"} vs {game.opponent || "computer"} &middot;{" "}
                {game.difficulty} &middot; {game.moves_count} moves
                {game.result_detail ? ` · ${game.result_detail.replace(/_/g, " ")}` : ""}
              </span>
              <span className="history__date">{new Date(game.created_at).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

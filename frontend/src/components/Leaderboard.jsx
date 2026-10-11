/**
 * Leaderboard panel: top players ranked by points (win = 1, draw = 0.5).
 *
 * Public data - just names and stats. Refreshes on the shared `game-saved`
 * window event so a finished game updates it alongside the history panel.
 */

import { useCallback, useEffect, useState } from "react";
import { authApi } from "../api/authClient.js";

const DIFFICULTIES = ["all", "easy", "medium", "hard", "master", "online"];
const MEDALS = ["\u{1F947}", "\u{1F948}", "\u{1F949}"]; // gold, silver, bronze

export default function Leaderboard() {
  const [entries, setEntries] = useState(null); // null = still loading
  const [difficulty, setDifficulty] = useState("all");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setEntries(await authApi.leaderboard(difficulty === "all" ? undefined : difficulty));
      setError("");
    } catch (err) {
      setEntries((previous) => previous ?? []);
      setError(err?.message || "Could not load the leaderboard.");
    }
  }, [difficulty]);

  useEffect(() => {
    setEntries(null);
    refresh();
    const onSaved = () => refresh();
    window.addEventListener("game-saved", onSaved);
    return () => window.removeEventListener("game-saved", onSaved);
  }, [refresh]);

  return (
    <section className="leaderboard" aria-label="Leaderboard">
      <div className="leaderboard__head">
        <h2>Leaderboard</h2>
        <label className="leaderboard__filter">
          <span>Difficulty</span>
          <select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
            {DIFFICULTIES.map((level) => (
              <option key={level} value={level}>
                {level === "all" ? "All levels" : level}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="leaderboard__error">{error}</p>}

      {entries === null ? (
        <p className="leaderboard__empty">Loading rankings…</p>
      ) : entries.length === 0 ? (
        <p className="leaderboard__empty">
          No games recorded yet at this level — be the first name on the board.
        </p>
      ) : (
        <ul className="leaderboard__list">
          {entries.map((entry) => (
            <li key={entry.user_id} className="leaderboard__row">
              <span className="leaderboard__rank">
                {entry.rank <= 3 ? MEDALS[entry.rank - 1] : `#${entry.rank}`}
              </span>
              <span className="leaderboard__name">
                {entry.name}
                <span className={`leaderboard__badge leaderboard__badge--${entry.provider}`}>
                  {entry.provider}
                </span>
              </span>
              <span className="leaderboard__record">
                {entry.wins}W&nbsp;{entry.draws}D&nbsp;{entry.losses}L
              </span>
              <span className="leaderboard__games">{entry.games} games</span>
              <span className="leaderboard__points">
                {entry.points} pt{entry.points === 1 ? "" : "s"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

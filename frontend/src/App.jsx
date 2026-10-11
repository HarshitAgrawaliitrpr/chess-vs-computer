import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import ChessGame from "./components/ChessGame.jsx";
import GameHistory from "./components/GameHistory.jsx";
import Leaderboard from "./components/Leaderboard.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import OnlinePlay from "./components/OnlinePlay.jsx";

function Shell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState("engine");
  const [joinCode, setJoinCode] = useState("");

  // Invite link support: /?join=CODE switches to the online tab and starts
  // the join; the parameter is stripped from the URL immediately so a
  // refresh does not re-trigger it.
  useEffect(() => {
    try {
      const code = new URLSearchParams(window.location.search).get("join");
      if (code) {
        setJoinCode(code.toUpperCase());
        setTab("online");
        const url = new URL(window.location.href);
        url.searchParams.delete("join");
        window.history.replaceState({}, "", url);
      }
    } catch {
      /* no URL API (tests) - ignore */
    }
  }, []);

  if (loading) {
    return (
      <div className="app">
        <p className="app__loading">Loading…</p>
      </div>
    );
  }
  if (!user) return <LoginScreen />;

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-row">
          <h1>Chess vs. Computer</h1>
          <div className="app__user">
            <span className="app__user-name" title={user.email || user.name}>
              {user.name}
            </span>
            <span className="app__user-email">{user.email || "guest account (no email)"}</span>
            <span className={`app__user-badge app__user-badge--${user.provider}`}>{user.provider}</span>
            <button type="button" className="app__logout" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
        <p>
          React + <code>react-chessboard</code> + <code>chess.js</code> &mdash; engine: minimax with
          alpha&#8209;beta pruning (FastAPI)
        </p>
      </header>

      <nav className="tabs" role="tablist" aria-label="Game mode">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "engine"}
          className={`tabs__tab ${tab === "engine" ? "tabs__tab--active" : ""}`}
          onClick={() => setTab("engine")}
        >
          vs Computer
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "online"}
          className={`tabs__tab ${tab === "online" ? "tabs__tab--active" : ""}`}
          onClick={() => setTab("online")}
        >
          Play Online
        </button>
      </nav>

      {tab === "engine" ? (
        <ChessGame />
      ) : (
        <OnlinePlay autoJoinCode={joinCode} onJoinConsumed={() => setJoinCode("")} />
      )}
      <GameHistory />
      <Leaderboard />
      <footer className="app__footer">
        <span className="app__credit">CREATED BY HARSHIT AGRAWAL WITH MIMO</span>
        <span>
          Move validation: castling, en passant, promotion, 50&#8209;move rule, threefold repetition
        </span>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}

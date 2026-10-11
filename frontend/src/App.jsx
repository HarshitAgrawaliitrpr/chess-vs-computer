import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import ChessGame from "./components/ChessGame.jsx";
import GameHistory from "./components/GameHistory.jsx";
import Leaderboard from "./components/Leaderboard.jsx";
import LoginScreen from "./components/LoginScreen.jsx";

function Shell() {
  const { user, loading, logout } = useAuth();

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
      <ChessGame />
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

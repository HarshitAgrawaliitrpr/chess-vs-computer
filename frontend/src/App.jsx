import ChessGame from "./components/ChessGame.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <h1>Chess vs. Computer</h1>
        <p>
          React + <code>react-chessboard</code> + <code>chess.js</code> &mdash; engine: minimax with
          alpha&#8209;beta pruning (FastAPI)
        </p>
      </header>
      <ChessGame />
      <footer className="app__footer">
        <span>Move validation: castling, en passant, promotion, 50&#8209;move rule, threefold repetition</span>
      </footer>
    </div>
  );
}
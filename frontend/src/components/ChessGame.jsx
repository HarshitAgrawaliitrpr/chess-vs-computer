import { Chessboard } from "react-chessboard";
import StatusBar from "./StatusBar.jsx";
import MoveHistory from "./MoveHistory.jsx";
import CapturedPieces from "./CapturedPieces.jsx";
import DifficultySelector from "./DifficultySelector.jsx";
import EngineStats from "./EngineStats.jsx";
import { useChessGame } from "../hooks/useChessGame.js";

export default function ChessGame() {
  const game = useChessGame();

  return (
    <div className="game">
      <section className="game__board">
        <Chessboard
          id="pve-board"
          position={game.fen}
          onPieceDrop={game.onPieceDrop}
          boardOrientation={game.boardOrientation}
          arePiecesDraggable={game.canMove}
          animationDuration={140}
          customDarkSquareStyle={{ backgroundColor: "#779556" }}
          customLightSquareStyle={{ backgroundColor: "#ebecd0" }}
          customBoardStyle={{ borderRadius: "6px", boxShadow: "0 8px 28px rgba(0,0,0,.45)" }}
        />
        <StatusBar status={game.status} thinking={game.thinking} error={game.error} />

        <div className="game__actions">
          <button type="button" onClick={() => game.startGame("w")} disabled={game.thinking}>
            Play as White
          </button>
          <button type="button" onClick={() => game.startGame("b")} disabled={game.thinking}>
            Play as Black
          </button>
          <button type="button" onClick={() => game.startGame(game.playerColor)} disabled={game.thinking}>
            Restart
          </button>
        </div>
      </section>

      <aside className="game__panel">
        <DifficultySelector value={game.difficulty} onChange={game.setDifficulty} disabled={game.thinking} />

        <CapturedPieces
          capturedByWhite={game.capturedByWhite}
          capturedByBlack={game.capturedByBlack}
          advantage={game.advantage}
        />

        <MoveHistory moves={game.moves} pgn={game.pgn} />

        <EngineStats info={game.engineInfo} thinking={game.thinking} />
      </aside>
    </div>
  );
}
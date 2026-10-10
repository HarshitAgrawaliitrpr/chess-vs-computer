import { useEffect, useState } from "react";
import { Chessboard } from "react-chessboard";
import StatusBar from "./StatusBar.jsx";
import MoveHistory from "./MoveHistory.jsx";
import CapturedPieces from "./CapturedPieces.jsx";
import DifficultySelector from "./DifficultySelector.jsx";
import EngineStats from "./EngineStats.jsx";
import GameOverOverlay from "./GameOverOverlay.jsx";
import { useChessGame } from "../hooks/useChessGame.js";

export default function ChessGame() {
  const game = useChessGame();
  const [resultDismissed, setResultDismissed] = useState(false);

  // A fresh game (or a color switch) always brings the dialog back next time.
  useEffect(() => {
    if (!game.status.over) setResultDismissed(false);
  }, [game.status.over]);

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

      {game.result && !resultDismissed && (
        <GameOverOverlay
          outcome={game.result}
          playerColor={game.playerColor}
          onRetry={() => game.startGame(game.playerColor)}
          onDismiss={() => setResultDismissed(true)}
        />
      )}
    </div>
  );
}
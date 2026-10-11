/**
 * Online tab: lobby (create/join) -> waiting room -> live board.
 *
 * Wraps useOnlineGame and reuses the shared panels (CapturedPieces,
 * MoveHistory, GameOverOverlay) so the layout matches the engine game.
 */

import { useState } from "react";
import { Chessboard } from "react-chessboard";
import CapturedPieces from "./CapturedPieces.jsx";
import GameOverOverlay from "./GameOverOverlay.jsx";
import MoveHistory from "./MoveHistory.jsx";
import { useOnlineGame } from "../hooks/useOnlineGame.js";

function Lobby({ game }) {
  const [code, setCode] = useState("");

  const submit = (event) => {
    event.preventDefault();
    const value = code.trim().toUpperCase();
    if (value.length === 6) void game.joinGame(value);
  };

  return (
    <div className="lobby">
      <section className="lobby__card">
        <h2>Play online</h2>
        <p>
          Create a game and share the invite code (or link) with a friend, or enter the code
          you received to join theirs. You play against a real person, and both of you keep the
          result in your history and the leaderboard.
        </p>
        <button type="button" className="lobby__primary" onClick={game.createGame} disabled={game.busy}>
          {game.busy ? "Working…" : "Create a game"}
        </button>

        <div className="lobby__divider">
          <span>or join with a code</span>
        </div>

        <form className="lobby__join" onSubmit={submit}>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            placeholder="Invite code"
            aria-label="Invite code"
            maxLength={6}
            autoComplete="off"
          />
          <button type="submit" disabled={game.busy || code.trim().length !== 6}>
            Join
          </button>
        </form>

        {game.error && <p className="lobby__error">{game.error}</p>}
      </section>
    </div>
  );
}

function WaitingRoom({ game }) {
  const [copied, setCopied] = useState(false);

  const inviteLink = `${window.location.origin}/?join=${game.server.code}`;

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(inviteLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable - the code below is still visible */
    }
  };

  return (
    <div className="lobby">
      <section className="lobby__card lobby__card--waiting">
        <h2>Waiting for your opponent…</h2>
        <p>Share this code so a friend can join:</p>
        <p className="lobby__code" aria-label="Invite code">
          {game.server.code}
        </p>
        <div className="lobby__actions">
          <button type="button" className="lobby__primary" onClick={copy}>
            {copied ? "Copied!" : "Copy invite link"}
          </button>
          <button type="button" onClick={game.cancelGame} disabled={game.busy}>
            Cancel game
          </button>
        </div>
        <p className="lobby__hint">This page updates automatically the moment they join.</p>
        {game.error && <p className="lobby__error">{game.error}</p>}
      </section>
    </div>
  );
}

export default function OnlinePlay({ autoJoinCode = "", onJoinConsumed }) {
  const game = useOnlineGame({ autoJoinCode, onJoinConsumed });
  const [dismissed, setDismissed] = useState(false);
  const server = game.server;

  if (!server) return <Lobby game={game} />;
  if (server.status === "waiting") return <WaitingRoom game={game} />;

  const colorName = server.my_color === "w" ? "White" : "Black";
  const over = server.status === "over";
  const turnText = over
    ? server.result_detail || "Game over"
    : game.myTurn
      ? game.inCheck
        ? "Your king is in check!"
        : "Your move"
      : `Waiting for ${server.opponent_name || "your opponent"}…`;

  const overlayText =
    server.result === "win"
      ? `You beat ${server.opponent_name || "your opponent"}!`
      : server.result === "loss"
        ? `${server.opponent_name || "Your opponent"} got you this round.`
        : undefined;

  return (
    <div className="game">
      <section className="game__board">
        <Chessboard
          id="online-board"
          position={game.position}
          onPieceDrop={game.onPieceDrop}
          boardOrientation={server.my_color === "b" ? "black" : "white"}
          arePiecesDraggable={game.canDrag}
          customSquareStyles={game.squareStyles}
          animationDuration={140}
          customDarkSquareStyle={{ backgroundColor: "#779556" }}
          customLightSquareStyle={{ backgroundColor: "#ebecd0" }}
          customBoardStyle={{ borderRadius: "6px", boxShadow: "0 8px 28px rgba(0,0,0,.45)" }}
        />

        <div className={`online__status ${game.myTurn ? "online__status--yourturn" : ""}`}>
          <span className="online__title">
            You play {colorName} vs {server.opponent_name || "opponent"}
          </span>
          <span className={`online__turn ${over ? "online__turn--over" : ""}`}>{turnText}</span>
          {game.error && <span className="online__error">{game.error}</span>}
        </div>

        <div className="game__actions">
          {over ? (
            <>
              <button type="button" className="online__new" onClick={game.leaveToLobby}>
                New game
              </button>
              <span className="online__invite">Invite code: {server.code}</span>
            </>
          ) : (
            <>
              <button type="button" onClick={game.resign} disabled={game.busy}>
                Resign
              </button>
              <span className="online__invite">Invite code: {server.code}</span>
            </>
          )}
        </div>
      </section>

      <aside className="game__panel">
        <CapturedPieces
          capturedByWhite={game.captures.capturedByWhite}
          capturedByBlack={game.captures.capturedByBlack}
          advantage={game.captures.advantage}
        />
        <MoveHistory moves={game.moves} pgn={server.pgn} />
        <section className="panel">
          <header className="panel__header">
            <h2>Game</h2>
          </header>
          <dl className="stats">
            <div>
              <dt>Opponent</dt>
              <dd>{server.opponent_name || "—"}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{server.status}</dd>
            </div>
            <div>
              <dt>Invite code</dt>
              <dd>{server.code}</dd>
            </div>
          </dl>
        </section>
      </aside>

      {over && server.result && !dismissed && (
        <GameOverOverlay
          outcome={server.result}
          playerColor={server.my_color}
          text={overlayText}
          onRetry={game.leaveToLobby}
          onDismiss={() => setDismissed(true)}
        />
      )}
    </div>
  );
}

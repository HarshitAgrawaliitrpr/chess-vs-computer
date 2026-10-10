/**
 * Core game state for the PvE chess UI.
 *
 * chess.js is the single source of truth for legality (castling, en passant,
 * promotion, check/checkmate are all validated there), while every move the
 * computer plays is requested from the FastAPI engine API.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { fetchComputerMove } from "../api/engineClient";

export const PIECE_SYMBOLS = {
  wp: "\u2659", wn: "\u2658", wb: "\u2657", wr: "\u2656", wq: "\u2655", wk: "\u2654",
  bp: "\u265F", bn: "\u265E", bb: "\u265D", br: "\u265C", bq: "\u265B", bk: "\u265A",
};

const PIECE_VALUES = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };

/** Derive a UI-friendly status object from a chess.js instance. */
function describeStatus(game) {
  const turn = game.turn() === "w" ? "white" : "black";
  if (game.isCheckmate()) {
    return { kind: "checkmate", over: true, turn, text: `Checkmate \u2014 ${turn === "white" ? "Black" : "White"} wins` };
  }
  if (game.isStalemate()) return { kind: "stalemate", over: true, turn, text: "Stalemate \u2014 draw" };
  if (game.isThreefoldRepetition()) return { kind: "draw", over: true, turn, text: "Draw \u2014 threefold repetition" };
  if (game.isInsufficientMaterial()) return { kind: "draw", over: true, turn, text: "Draw \u2014 insufficient material" };
  if (game.isDrawByFiftyMoves?.() || game.isDraw()) return { kind: "draw", over: true, turn, text: "Draw" };
  if (game.isCheck()) return { kind: "check", over: false, turn, text: `Check \u2014 ${turn} to move` };
  return { kind: "active", over: false, turn, text: `${turn} to move` };
}

/** Split the SAN history into `{capturedByWhite, capturedByBlack}` piece codes. */
function summarizeCaptures(verboseHistory) {
  const capturedByWhite = [];
  const capturedByBlack = [];
  for (const move of verboseHistory) {
    if (!move.captured) continue;
    const capturedColor = move.color === "w" ? "b" : "w";
    if (move.color === "w") capturedByWhite.push(`${capturedColor}${move.captured}`);
    else capturedByBlack.push(`${capturedColor}${move.captured}`);
  }
  const score = (codes) => codes.reduce((sum, code) => sum + (PIECE_VALUES[code[1]] ?? 0), 0);
  return { capturedByWhite, capturedByBlack, advantage: score(capturedByWhite) - score(capturedByBlack) };
}

/**
 * Player-centric outcome of a finished game: `"win" | "loss" | "draw"`.
 * Only checkmate has a winner; every draw variant reports `"draw"`.
 * Returns `null` while the game is still running.
 */
function describeResult(status, playerColor) {
  if (!status.over) return null;
  if (status.kind !== "checkmate") return "draw";
  // On checkmate the mated side is the one to move, so the winner is the other color.
  const winner = status.turn === "white" ? "black" : "white";
  const playerSide = playerColor === "b" ? "black" : "white";
  return winner === playerSide ? "win" : "loss";
}

function snapshot(game) {
  const verbose = game.history({ verbose: true });
  const captures = summarizeCaptures(verbose);
  return {
    fen: game.fen(),
    pgn: game.pgn(),
    moves: game.history(),
    status: describeStatus(game),
    ...captures,
  };
}

/**
 * @param {{playerColor?: "w"|"b", difficulty?: string, engine?: Function}} options
 */
export function useChessGame({
  playerColor: initialColor = "w",
  difficulty: initialDifficulty = "medium",
  engine = fetchComputerMove,
} = {}) {
  const gameRef = useRef(null);
  if (gameRef.current === null) gameRef.current = new Chess();

  const [gameState, setGameState] = useState(() => snapshot(gameRef.current));
  const [playerColor, setPlayerColorState] = useState(initialColor);
  const [difficulty, setDifficultyState] = useState(initialDifficulty);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState(null);
  const [engineInfo, setEngineInfo] = useState(null);

  // Refs keep async callbacks free of stale closures.
  const busyRef = useRef(false);
  const colorRef = useRef(initialColor);
  const difficultyRef = useRef(initialDifficulty);
  const engineRef = useRef(engine);
  engineRef.current = engine;

  const commit = useCallback(() => setGameState(snapshot(gameRef.current)), []);

  /** Ask the engine to play the side to move in the current position. */
  const requestComputerMove = useCallback(async () => {
    const game = gameRef.current;
    if (busyRef.current || game.isGameOver()) return;
    busyRef.current = true;
    setThinking(true);
    setError(null);
    try {
      const result = await engineRef.current({
        fen: game.fen(),
        difficulty: difficultyRef.current,
      });
      game.move({
        from: result.move.from,
        to: result.move.to,
        promotion: result.move.promotion ?? "q",
      });
      setEngineInfo({
        san: result.move.san,
        score: result.score,
        scoreType: result.score_type,
        mateIn: result.mate_in,
        depth: result.depth,
        nodes: result.nodes,
        timeMs: result.time_ms,
        pv: result.pv,
        elo: result.elo_estimate,
      });
      commit();
    } catch (err) {
      setError(err?.message ?? String(err));
    } finally {
      busyRef.current = false;
      setThinking(false);
    }
  }, [commit]);

  /** react-chessboard drop handler: returns `false` when the move is illegal. */
  const onPieceDrop = useCallback(
    (source, target) => {
      const game = gameRef.current;
      if (busyRef.current || gameState.status.over || game.turn() !== colorRef.current) return false;

      let move = null;
      try {
        move = game.move({ from: source, to: target });
      } catch {
        try {
          // Only reachable for pawn promotions.
          move = game.move({ from: source, to: target, promotion: "q" });
        } catch {
          return false; // illegal move - keep the piece where it was
        }
      }
      if (!move) return false;

      commit();
      if (!game.isGameOver()) void requestComputerMove();
      return true;
    },
    [commit, gameState.status.over, requestComputerMove],
  );

  /** (Re)start a game; when the human plays Black the engine opens as White. */
  const startGame = useCallback(
    (color = colorRef.current) => {
      colorRef.current = color;
      setPlayerColorState(color);
      gameRef.current = new Chess();
      setEngineInfo(null);
      setError(null);
      commit();
      if (color === "b") void requestComputerMove();
    },
    [commit, requestComputerMove],
  );

  const setPlayerColor = useCallback((color) => startGame(color), [startGame]);

  const setDifficulty = useCallback((next) => {
    difficultyRef.current = next;
    setDifficultyState(next);
  }, []);

  /** Load an arbitrary FEN (used by tests / advanced setups). */
  const loadFen = useCallback(
    (fen) => {
      gameRef.current = new Chess(fen);
      setEngineInfo(null);
      setError(null);
      commit();
    },
    [commit],
  );

  const boardOrientation = useMemo(() => (playerColor === "b" ? "black" : "white"), [playerColor]);

  return {
    ...gameState,
    playerColor,
    boardOrientation,
    difficulty,
    thinking,
    error,
    engineInfo,
    result: describeResult(gameState.status, playerColor),
    canMove: !gameState.status.over && !thinking && gameState.status.turn === (playerColor === "b" ? "black" : "white"),
    onPieceDrop,
    startGame,
    setPlayerColor,
    setDifficulty,
    loadFen,
    requestComputerMove,
  };
}
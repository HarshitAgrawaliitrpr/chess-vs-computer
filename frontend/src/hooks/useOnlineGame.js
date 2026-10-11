/**
 * State + transport for one online (human vs human) game.
 *
 * The server is authoritative: every position comes from Turso, moves are
 * validated server-side with python-chess, and the client polls while the
 * game is waiting or active (paused when the tab is hidden). A single game
 * id is kept in localStorage so a refresh resumes the match.
 *
 * `server.moves` (SAN from the API) is replayed through chess.js to get
 * legality checks for drops, captured-piece stats and move history.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { onlineApi } from "../api/onlineClient.js";
import { summarizeCaptures } from "./useChessGame.js";

const STORAGE_KEY = "chess_online_game";
const POLL_MS = 2500;

const persist = (gameId) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, gameId);
  } catch {
    /* storage disabled - resume across refresh just won't work */
  }
};

const forget = () => {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
};

/** Replay server SAN moves; fall back to the raw FEN if anything is off. */
function rebuild(server) {
  const chess = new Chess();
  const verbose = [];
  if (server.moves?.length) {
    try {
      for (const san of server.moves) {
        const move = chess.move(san);
        if (move) verbose.push(move);
      }
    } catch {
      let fallback;
      try {
        fallback = new Chess(server.fen);
      } catch {
        fallback = new Chess();
      }
      return { chess: fallback, verbose: [] };
    }
  }
  return { chess, verbose };
}

/**
 * @param {{autoJoinCode?: string, onJoinConsumed?: () => void}} options
 */
export function useOnlineGame({ autoJoinCode = "", onJoinConsumed } = {}) {
  const [server, setServer] = useState(null); // null = lobby
  const [position, setPosition] = useState(null); // FEN for the board
  const [verboseMoves, setVerboseMoves] = useState([]);
  const [inCheck, setInCheck] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const chessRef = useRef(new Chess());
  const wasOverRef = useRef(false);
  const autoJoinRanRef = useRef(false);

  const apply = useCallback((next) => {
    const rebuilt = rebuild(next);
    chessRef.current = rebuilt.chess;
    setServer(next);
    setPosition(next.fen);
    setVerboseMoves(rebuilt.verbose);
    setInCheck(rebuilt.chess.isCheck());
    setError("");
    // The server writes both players' history rows itself; just tell the
    // history + leaderboard panels to refresh when the game ends.
    if (next.status === "over") {
      if (!wasOverRef.current) {
        wasOverRef.current = true;
        window.dispatchEvent(new CustomEvent("game-saved"));
      }
    } else {
      wasOverRef.current = false;
    }
  }, []);

  // ---- polling loop (waiting/active only, paused while hidden) ----
  useEffect(() => {
    if (!server || (server.status !== "waiting" && server.status !== "active")) return undefined;
    let cancelled = false;
    let timer = null;

    const pull = async () => {
      try {
        const next = await onlineApi.state(server.id);
        if (!cancelled) apply(next);
      } catch {
        /* transient network error - keep polling */
      }
      if (!cancelled) timer = setTimeout(pull, POLL_MS);
    };
    const onVisibility = () => {
      if (!document.hidden) void pull();
    };

    document.addEventListener("visibilitychange", onVisibility);
    timer = setTimeout(pull, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [server, apply]);

  // ---- resume an interrupted game after refresh ----
  useEffect(() => {
    let stored = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    if (!stored) return undefined;
    let cancelled = false;
    onlineApi
      .state(stored)
      .then((next) => {
        if (!cancelled) {
          if (next.status === "cancelled") forget();
          else apply(next);
        }
      })
      .catch(() => {
        if (!cancelled) forget(); // gone or not ours anymore
      });
    return () => {
      cancelled = true;
    };
  }, [apply]);

  // ---- auto-join from an invite link (?join=CODE) ----
  useEffect(() => {
    if (!autoJoinCode || autoJoinRanRef.current) return;
    autoJoinRanRef.current = true;
    void (async () => {
      setBusy(true);
      setError("");
      try {
        const next = await onlineApi.join(autoJoinCode);
        persist(next.id);
        apply(next);
      } catch (err) {
        setError(err?.message || "Could not join that game.");
      } finally {
        setBusy(false);
        onJoinConsumed?.();
      }
    })();
  }, [autoJoinCode, onJoinConsumed, apply]);

  // ---- lobby actions ----
  const createGame = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const next = await onlineApi.create();
      persist(next.id);
      apply(next);
    } catch (err) {
      setError(err?.message || "Could not create a game.");
    } finally {
      setBusy(false);
    }
  }, [apply]);

  const joinGame = useCallback(
    async (code) => {
      setBusy(true);
      setError("");
      try {
        const next = await onlineApi.join(code);
        persist(next.id);
        apply(next);
      } catch (err) {
        setError(err?.message || "Could not join that game.");
      } finally {
        setBusy(false);
      }
    },
    [apply],
  );

  const resign = useCallback(async () => {
    if (!server) return;
    setBusy(true);
    setError("");
    try {
      apply(await onlineApi.resign(server.id));
    } catch (err) {
      setError(err?.message || "Could not resign.");
    } finally {
      setBusy(false);
    }
  }, [server, apply]);

  const cancelGame = useCallback(async () => {
    if (!server) return;
    setBusy(true);
    setError("");
    try {
      await onlineApi.cancel(server.id);
      forget();
      wasOverRef.current = false;
      setServer(null);
      setPosition(null);
      setVerboseMoves([]);
    } catch (err) {
      setError(err?.message || "Could not cancel the game.");
    } finally {
      setBusy(false);
    }
  }, [server]);

  const leaveToLobby = useCallback(() => {
    forget();
    wasOverRef.current = false;
    setServer(null);
    setPosition(null);
    setVerboseMoves([]);
    setError("");
  }, []);

  // ---- board interaction ----
  const onPieceDrop = useCallback(
    (source, target) => {
      if (!server || server.status !== "active" || busy) return false;
      if (server.turn !== server.my_color) return false;

      const chess = chessRef.current;
      let played = null;
      try {
        played = chess.move({ from: source, to: target });
      } catch {
        try {
          played = chess.move({ from: source, to: target, promotion: "q" });
        } catch {
          return false; // illegal - keep the piece where it was
        }
      }
      if (!played) return false;

      // Optimistic update; the server response is the source of truth.
      setPosition(chess.fen());
      setVerboseMoves(chess.history({ verbose: true }));
      setInCheck(chess.isCheck());

      setBusy(true);
      setError("");
      onlineApi
        .move(server.id, {
          from: source,
          to: target,
          ...(played.promotion ? { promotion: played.promotion } : {}),
        })
        .then(apply)
        .catch(async (err) => {
          setError(err?.message || "Move rejected.");
          try {
            apply(await onlineApi.state(server.id)); // roll back to server truth
          } catch {
            /* ignore */
          }
        })
        .finally(() => setBusy(false));
      return true;
    },
    [server, busy, apply],
  );

  // ---- derived view state ----
  const captures = useMemo(() => summarizeCaptures(verboseMoves), [verboseMoves]);
  const moves = useMemo(() => verboseMoves.map((move) => move.san), [verboseMoves]);
  const myTurn = Boolean(server && server.status === "active" && server.turn === server.my_color);
  const squareStyles = useMemo(() => {
    const uci = server?.last_move;
    if (!uci || uci.length < 4) return {};
    const tint = { backgroundColor: "rgba(247, 246, 102, 0.55)" };
    return { [uci.slice(0, 2)]: tint, [uci.slice(2, 4)]: tint };
  }, [server?.last_move]);

  return {
    server,
    position,
    moves,
    captures,
    error,
    busy,
    inCheck,
    myTurn,
    canDrag: myTurn && !busy,
    squareStyles,
    onPieceDrop,
    createGame,
    joinGame,
    resign,
    cancelGame,
    leaveToLobby,
  };
}

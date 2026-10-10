import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useChessGame } from "../hooks/useChessGame.js";

/** Flush the async engine round-trip with a generous timeout. */
const wait = (assertion) => waitFor(assertion, { timeout: 5000 });

const engineReplyFor = (move) => ({
  move,
  fen: "unused",
  score: 25,
  score_type: "cp",
  mate_in: null,
  depth: 3,
  nodes: 1234,
  time_ms: 42,
  pv: [],
  difficulty: "medium",
  elo_estimate: 1250,
});

const E5 = { from: "e7", to: "e5", san: "e5", uci: "e7e5", promotion: null };
const D5 = { from: "d7", to: "d5", san: "d5", uci: "d7d5", promotion: null };

/** A scripted fake engine: replies with moves from the queue in order. */
function fakeEngine(script = []) {
  const queue = [...script];
  return vi.fn(async () => engineReplyFor(queue.shift() ?? E5));
}

describe("useChessGame", () => {
  it("applies a legal human move and triggers the engine reply", async () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => {
      expect(result.current.onPieceDrop("e2", "e4")).toBe(true);
    });

    expect(result.current.moves).toContain("e4");
    await wait(() => expect(engine).toHaveBeenCalledTimes(1));
    await wait(() => expect(result.current.moves).toContain("e5"));
    expect(result.current.moves).toEqual(["e4", "e5"]);
  });

  it("rejects an illegal move (chess.js validation)", () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => {
      expect(result.current.onPieceDrop("e2", "e5")).toBe(false); // not a legal pawn move
      expect(result.current.onPieceDrop("a2", "a3")).toBe(true);
    });
    // Only the legal move advanced the position.
    expect(result.current.moves).toEqual(["a3"]);
  });

  it("keeps the move history in PGN order", async () => {
    const engine = fakeEngine([E5, D5]);
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.onPieceDrop("e2", "e4"));
    await wait(() => expect(result.current.moves).toEqual(["e4", "e5"]));

    act(() => result.current.onPieceDrop("d2", "d4"));
    await wait(() => expect(result.current.moves).toEqual(["e4", "e5", "d4", "d5"]));

    expect(result.current.pgn).toContain("1. e4 e5");
    expect(result.current.pgn).toContain("2. d4 d5");
  });

  it("records captured pieces and material advantage", async () => {
    const engine = fakeEngine([D5]);
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.onPieceDrop("e2", "e4")); // 1. e4
    await wait(() => expect(result.current.moves).toEqual(["e4", "d5"]));
    act(() => result.current.onPieceDrop("e4", "d5")); // 2. exd5
    await wait(() => expect(result.current.capturedByWhite).toContain("bp"));

    expect(result.current.advantage).toBe(1);
  });

  it("detects checkmate and blocks further moves", async () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    // Back-rank mate in one: 1. Ra8#
    act(() => result.current.loadFen("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"));
    act(() => {
      expect(result.current.onPieceDrop("a1", "a8")).toBe(true);
    });

    expect(result.current.status.kind).toBe("checkmate");
    expect(result.current.status.over).toBe(true);

    // No further interaction (and no engine call) once the game is over.
    const callsBefore = engine.mock.calls.length;
    act(() => {
      expect(result.current.onPieceDrop("g7", "g6")).toBe(false);
    });
    expect(engine.mock.calls.length).toBe(callsBefore);
  });

  it("handles pawn promotion to a queen", () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.loadFen("8/4P3/8/8/8/8/2k5/K7 w - - 0 1"));
    act(() => {
      expect(result.current.onPieceDrop("e7", "e8")).toBe(true);
    });

    expect(result.current.moves[0]).toBe("e8=Q");
  });

  it("en passant is accepted and captures the passing pawn", async () => {
    const engine = fakeEngine([
      { from: "d7", to: "d5", san: "d5", uci: "d7d5", promotion: null },
      { from: "a7", to: "a6", san: "a6", uci: "a7a6", promotion: null },
    ]);
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.onPieceDrop("e2", "e4")); // 1. e4
    await wait(() => expect(result.current.moves).toEqual(["e4", "d5"]));
    act(() => result.current.onPieceDrop("e4", "d5")); // 2. exd5
    await wait(() => expect(result.current.moves).toHaveLength(3));

    // 2... a6 is scripted; now exercise a genuine en passant capture: the
    // black pawn has just played d7-d5 next to a white pawn on e5.
    await wait(() => expect(result.current.moves).toHaveLength(4));
    act(() => result.current.loadFen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"));
    act(() => {
      expect(result.current.onPieceDrop("e5", "d6")).toBe(true); // exd6 e.p.
    });
    expect(result.current.moves.at(-1)).toBe("exd6");
    expect(result.current.capturedByWhite).toContain("bp");
  });

  it("restarting as Black makes the engine open as White", async () => {
    // The engine plays White's first move when the human takes Black.
    const engine = fakeEngine([{ from: "e2", to: "e4", san: "e4", uci: "e2e4", promotion: null }]);
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.startGame("b"));

    await wait(() => expect(engine).toHaveBeenCalledTimes(1));
    await wait(() => expect(result.current.moves).toHaveLength(1)); // engine opened as White
    expect(result.current.playerColor).toBe("b");
    expect(result.current.boardOrientation).toBe("black");
    expect(result.current.status.turn).toBe("black"); // back to the human (Black)
    expect(result.current.canMove).toBe(true);
  });

  it("reports an API failure without corrupting the position", async () => {
    const engine = vi.fn().mockRejectedValue(new Error("Engine request failed (HTTP 500)"));
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => result.current.onPieceDrop("e2", "e4"));

    await wait(() => expect(result.current.error).toContain("HTTP 500"));
    expect(result.current.moves).toEqual(["e4"]); // human move kept, no bogus engine move
    expect(result.current.thinking).toBe(false);
  });

  it("exposes canMove only on the human's turn", async () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine, playerColor: "w" }));

    expect(result.current.canMove).toBe(true);
    act(() => result.current.onPieceDrop("e2", "e4"));
    // While the engine replies the human may not move again.
    expect(result.current.canMove).toBe(false);
    await wait(() => expect(result.current.moves).toEqual(["e4", "e5"]));
    expect(result.current.canMove).toBe(true);
  });

  // ---- result classification (drives the win/loss overlay) ----

  const BACK_RANK_MATE = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1";
  const STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1";

  it("reports a win when the human delivers checkmate, and clears on restart", () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine, playerColor: "w" }));

    expect(result.current.result).toBeNull(); // game still running

    act(() => result.current.loadFen(BACK_RANK_MATE));
    act(() => {
      expect(result.current.onPieceDrop("a1", "a8")).toBe(true); // 1. Ra8#
    });

    expect(result.current.status.kind).toBe("checkmate");
    expect(result.current.result).toBe("win");

    act(() => result.current.startGame("w")); // retry from the overlay
    expect(result.current.result).toBeNull();
    expect(result.current.moves).toEqual([]);
  });

  it("reports a loss when the engine delivers checkmate", async () => {
    const engine = fakeEngine([{ from: "a1", to: "a8", san: "Ra8", uci: "a1a8", promotion: null }]);
    const { result } = renderHook(() => useChessGame({ engine, playerColor: "b" }));

    act(() => result.current.loadFen(BACK_RANK_MATE));
    act(() => {
      void result.current.requestComputerMove(); // computer (White) delivers mate
    });

    await wait(() => expect(result.current.status.kind).toBe("checkmate"));
    expect(result.current.result).toBe("loss");
  });

  it("classifies every draw variant as a draw", () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine, playerColor: "w" }));

    act(() => result.current.loadFen(STALEMATE)); // stalemate
    expect(result.current.status.kind).toBe("stalemate");
    expect(result.current.result).toBe("draw");
  });

  // ---- pre-moves ----

  it("queues a pre-move while the engine replies and plays it automatically", async () => {
    const engine = fakeEngine([
      { from: "e7", to: "e5", san: "e5", uci: "e7e5", promotion: null },
      { from: "d7", to: "d5", san: "d5", uci: "d7d5", promotion: null },
    ]);
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => {
      expect(result.current.onPieceDrop("e2", "e4")).toBe(true); // real move
      // Immediately queue a pre-move while the computer is thinking:
      expect(result.current.onPieceDrop("d2", "d4")).toBe(false); // not applied yet
    });

    expect(result.current.preMove).toEqual({ from: "d2", to: "d4" });
    expect(result.current.moves).toEqual(["e4"]); // position untouched

    // The fake engine resolves instantly, so assert the fully settled state:
    // e4 - e5, pre-move d4 fires, engine answers d5.
    await wait(() => expect(result.current.moves).toEqual(["e4", "e5", "d4", "d5"]));
    expect(result.current.preMove).toBeNull();
    expect(result.current.squareStyles).toEqual({}); // highlights cleared
  });

  it("discards a pre-move that became illegal after the reply", async () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => {
      expect(result.current.onPieceDrop("e2", "e4")).toBe(true);
      // Illegal 3-square pawn push, queued blindly (a2 still has its pawn):
      expect(result.current.onPieceDrop("a2", "a5")).toBe(false);
    });
    expect(result.current.preMove).toEqual({ from: "a2", to: "a5" });

    await wait(() => expect(result.current.moves).toEqual(["e4", "e5"]));
    expect(result.current.preMove).toBeNull(); // rejected on execution
    expect(result.current.moves).toEqual(["e4", "e5"]); // no phantom move
    expect(engine).toHaveBeenCalledTimes(1); // engine only played its single reply
  });

  it("only accepts own pieces for a pre-move and can cancel it", async () => {
    const engine = fakeEngine();
    const { result } = renderHook(() => useChessGame({ engine }));

    act(() => {
      expect(result.current.onPieceDrop("e2", "e4")).toBe(true);
      // Dragging an opponent piece must never be queued:
      expect(result.current.onPieceDrop("e7", "e5")).toBe(false);
    });
    expect(result.current.preMove).toBeNull();

    // A second pre-move replaces the first (each act flushes the state):
    act(() => result.current.onPieceDrop("g1", "f3"));
    expect(result.current.preMove).toEqual({ from: "g1", to: "f3" });
    act(() => result.current.onPieceDrop("c2", "c4"));
    expect(result.current.preMove).toEqual({ from: "c2", to: "c4" });
    expect(result.current.squareStyles.c2).toBeTruthy();
    expect(result.current.squareStyles.c4).toBeTruthy();

    act(() => result.current.clearPreMove());
    expect(result.current.preMove).toBeNull();
    expect(result.current.squareStyles).toEqual({});

    await wait(() => expect(result.current.moves).toEqual(["e4", "e5"]));
    expect(result.current.moves).toEqual(["e4", "e5"]); // cancelled pre-move never fires
  });

  it("lets a Black player pre-move while the computer opens", async () => {
    const engine = fakeEngine([
      { from: "e2", to: "e4", san: "e4", uci: "e2e4", promotion: null },
      { from: "c2", to: "c4", san: "c4", uci: "c2c4", promotion: null },
    ]);
    const { result } = renderHook(() => useChessGame({ engine, playerColor: "b" }));

    act(() => {
      result.current.startGame("b"); // computer opens as White
      expect(result.current.onPieceDrop("d7", "d5")).toBe(false); // queued immediately
    });
    expect(result.current.preMove).toEqual({ from: "d7", to: "d5" });

    // Opening e4, pre-move d5 fires, computer answers c4 — settled state:
    await wait(() => expect(result.current.moves).toEqual(["e4", "d5", "c4"]));
    expect(result.current.preMove).toBeNull();
    expect(result.current.canMove).toBe(true); // back to the human
  });
});
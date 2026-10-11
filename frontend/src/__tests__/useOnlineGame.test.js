import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useOnlineGame } from "../hooks/useOnlineGame.js";
import { onlineApi } from "../api/onlineClient.js";

vi.mock("../api/onlineClient.js", () => ({
  onlineApi: {
    create: vi.fn(),
    join: vi.fn(),
    state: vi.fn(),
    move: vi.fn(),
    resign: vi.fn(),
    cancel: vi.fn(),
  },
}));

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const makeServer = (overrides = {}) => ({
  id: "g1",
  code: "ABCDEF",
  status: "waiting",
  fen: START_FEN,
  pgn: "",
  moves: [],
  last_move: null,
  my_color: "w",
  white_name: "Alice",
  black_name: null,
  opponent_name: null,
  turn: "w",
  winner: null,
  result: null,
  result_detail: null,
  created_at: "2026-10-11T10:00:00Z",
  updated_at: "2026-10-11T10:00:00Z",
  ...overrides,
});

describe("useOnlineGame", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("creates a game and remembers it for refresh-resume", async () => {
    onlineApi.create.mockResolvedValue(makeServer());

    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.createGame();
    });

    expect(onlineApi.create).toHaveBeenCalledTimes(1);
    expect(result.current.server.status).toBe("waiting");
    expect(result.current.server.code).toBe("ABCDEF");
    expect(window.localStorage.getItem("chess_online_game")).toBe("g1");
  });

  it("joins by code and switches to the active game", async () => {
    onlineApi.join.mockResolvedValue(
      makeServer({
        status: "active",
        my_color: "b",
        black_name: "Bob",
        opponent_name: "Alice",
        turn: "w",
      }),
    );

    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.joinGame("abcdef");
    });

    expect(onlineApi.join).toHaveBeenCalledWith("abcdef");
    expect(result.current.server.status).toBe("active");
    expect(result.current.server.my_color).toBe("b");
    expect(result.current.myTurn).toBe(false); // white (Alice) is to move
    expect(result.current.canDrag).toBe(false);
  });

  it("surfaces join errors without leaving the lobby", async () => {
    onlineApi.join.mockRejectedValue(new Error("No game with that invite code."));

    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.joinGame("ZZZZZZ");
    });

    expect(result.current.error).toBe("No game with that invite code.");
    expect(result.current.server).toBeNull();
  });

  it("posts a legal move and applies the server response", async () => {
    // Creator's view right after the opponent joined: active, our turn (white).
    onlineApi.create.mockResolvedValue(
      makeServer({ status: "active", black_name: "Bob", opponent_name: "Bob", turn: "w" }),
    );
    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.createGame();
    });
    expect(result.current.myTurn).toBe(true);

    onlineApi.move.mockResolvedValue(
      makeServer({
        status: "active",
        black_name: "Bob",
        opponent_name: "Bob",
        turn: "b",
        fen: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        moves: ["e4"],
        last_move: "e2e4",
        pgn: "1. e4",
      }),
    );

    let dropped;
    await act(async () => {
      dropped = result.current.onPieceDrop("e2", "e4");
    });

    expect(dropped).toBe(true);
    await waitFor(() => expect(onlineApi.move).toHaveBeenCalledTimes(1));
    expect(onlineApi.move).toHaveBeenCalledWith("g1", { from: "e2", to: "e4" });
    await waitFor(() => expect(result.current.server.moves).toEqual(["e4"]));
    expect(result.current.server.turn).toBe("b");
    expect(result.current.myTurn).toBe(false);
  });

  it("refuses drops when it is not your turn", async () => {
    onlineApi.join.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", turn: "w", black_name: "Bob" }),
    );
    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.joinGame("ABCDEF");
    });

    expect(result.current.onPieceDrop("e7", "e5")).toBe(false);
    expect(onlineApi.move).not.toHaveBeenCalled();
  });

  it("polls for the opponent's move while active", async () => {
    vi.useFakeTimers();
    onlineApi.join.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", turn: "w", black_name: "Bob" }),
    );
    onlineApi.state.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", turn: "b", black_name: "Bob", moves: ["e4"] }),
    );

    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.joinGame("ABCDEF");
    });
    expect(onlineApi.state).not.toHaveBeenCalled();

    // waitFor cannot be used under fake timers (it polls a faked setTimeout);
    // advanceTimersByTimeAsync flushes the callback AND its microtasks.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2600);
    });

    expect(onlineApi.state).toHaveBeenCalledWith("g1");
    expect(result.current.server.moves).toEqual(["e4"]);
  });

  it("resumes a stored game on mount and forgets unknown ids", async () => {
    window.localStorage.setItem("chess_online_game", "gone");
    onlineApi.state.mockRejectedValue(new Error("Game not found."));

    renderHook(() => useOnlineGame());
    await waitFor(() => expect(onlineApi.state).toHaveBeenCalledWith("gone"));
    await waitFor(() =>
      expect(window.localStorage.getItem("chess_online_game")).toBeNull(),
    );
  });

  it("announces game over with a game-saved event for history + leaderboard", async () => {
    onlineApi.create.mockResolvedValue(
      makeServer({ status: "active", black_name: "Bob", opponent_name: "Bob", turn: "w" }),
    );
    const { result } = renderHook(() => useOnlineGame());
    await act(async () => {
      await result.current.createGame();
    });

    const seen = [];
    const listener = (event) => seen.push(event.type);
    window.addEventListener("game-saved", listener);

    onlineApi.move.mockResolvedValue(
      makeServer({
        status: "over",
        winner: "b",
        result: "loss",
        result_detail: "checkmate",
        turn: "w",
        black_name: "Bob",
        opponent_name: "Bob",
        moves: ["f3", "e5", "g4", "Qh4#"],
        last_move: "d8h4",
      }),
    );

    await act(async () => {
      result.current.onPieceDrop("f2", "f3");
    });
    await waitFor(() => expect(result.current.server.status).toBe("over"));

    expect(seen).toContain("game-saved");
    expect(result.current.server.result).toBe("loss");
    window.removeEventListener("game-saved", listener);
  });
});

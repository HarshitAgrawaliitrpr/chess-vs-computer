import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OnlinePlay from "../components/OnlinePlay.jsx";
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

// react-chessboard needs layout APIs jsdom does not provide.
vi.mock("react-chessboard", () => ({
  Chessboard: () => <div data-testid="board" />,
}));

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const makeServer = (overrides = {}) => ({
  id: "g1",
  code: "K7XQ2M",
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

describe("OnlinePlay", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it("shows the lobby with create and join actions", () => {
    render(<OnlinePlay />);
    expect(screen.getByText("Play online")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create a game" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Join" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Join" }).disabled).toBe(true);
  });

  it("creates a game and shows the waiting room with the invite code", async () => {
    const user = userEvent.setup();
    onlineApi.create.mockResolvedValue(makeServer());

    render(<OnlinePlay />);
    await user.click(screen.getByRole("button", { name: "Create a game" }));

    expect(await screen.findByText("Waiting for your opponent…")).toBeTruthy();
    expect(screen.getByLabelText("Invite code").textContent).toBe("K7XQ2M");
    expect(screen.getByRole("button", { name: "Copy invite link" })).toBeTruthy();
    expect(window.localStorage.getItem("chess_online_game")).toBe("g1");
  });

  it("joins with the typed code, uppercased", async () => {
    const user = userEvent.setup();
    onlineApi.join.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", black_name: "Bob", opponent_name: "Alice" }),
    );

    render(<OnlinePlay />);
    const input = screen.getByRole("textbox", { name: "Invite code" });
    await user.type(input, "k7xq2m");
    await user.click(screen.getByRole("button", { name: "Join" }));

    await waitFor(() => expect(onlineApi.join).toHaveBeenCalledWith("K7XQ2M"));
    expect(await screen.findByTestId("board")).toBeTruthy();
    expect(screen.getByText(/You play Black vs Alice/)).toBeTruthy();
    // it is White's turn (the creator's), so no dragging and no resign loop
    expect(screen.getByText("Waiting for Alice…")).toBeTruthy();
  });

  it("shows the server error when joining fails", async () => {
    const user = userEvent.setup();
    onlineApi.join.mockRejectedValue(new Error("No game with that invite code."));

    render(<OnlinePlay />);
    await user.type(screen.getByRole("textbox", { name: "Invite code" }), "ZZZZZZ");
    await user.click(screen.getByRole("button", { name: "Join" }));

    expect(await screen.findByText("No game with that invite code.")).toBeTruthy();
    expect(screen.getByText("Play online")).toBeTruthy(); // still in the lobby
  });

  it("runs an auto-join for an invite link exactly once", async () => {
    onlineApi.join.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", black_name: "Bob", opponent_name: "Alice" }),
    );

    render(<OnlinePlay autoJoinCode="K7XQ2M" onJoinConsumed={() => {}} />);
    await waitFor(() => expect(onlineApi.join).toHaveBeenCalledWith("K7XQ2M"));
    expect(onlineApi.join).toHaveBeenCalledTimes(1);
  });

  it("offers resign during an active game", async () => {
    const user = userEvent.setup();
    onlineApi.join.mockResolvedValue(
      makeServer({ status: "active", my_color: "b", black_name: "Bob", opponent_name: "Alice" }),
    );
    onlineApi.resign.mockResolvedValue(
      makeServer({
        status: "over",
        my_color: "b",
        black_name: "Bob",
        opponent_name: "Alice",
        winner: "w",
        result: "loss",
        result_detail: "resignation",
        turn: "b",
      }),
    );

    render(<OnlinePlay />);
    await user.type(screen.getByRole("textbox", { name: "Invite code" }), "K7XQ2M");
    await user.click(screen.getByRole("button", { name: "Join" }));
    expect(await screen.findByTestId("board")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Resign" }));
    await waitFor(() => expect(onlineApi.resign).toHaveBeenCalledWith("g1"));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByText("Better luck next time")).toBeTruthy();
    expect(screen.getByText(/Alice got you this round/)).toBeTruthy();
  });
});

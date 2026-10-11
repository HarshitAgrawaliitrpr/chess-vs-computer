import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authApi } from "../api/authClient.js";
import Leaderboard from "../components/Leaderboard.jsx";

vi.mock("../api/authClient.js", () => ({
  authApi: {
    leaderboard: vi.fn(),
  },
}));

const SAMPLE = [
  {
    rank: 1,
    user_id: "u1",
    name: "Mia",
    provider: "email",
    games: 4,
    wins: 3,
    draws: 1,
    losses: 0,
    points: 3.5,
    win_rate: 75,
  },
  {
    rank: 2,
    user_id: "u2",
    name: "Guest-7F3A",
    provider: "guest",
    games: 2,
    wins: 1,
    draws: 0,
    losses: 1,
    points: 1,
    win_rate: 50,
  },
  {
    rank: 4,
    user_id: "u4",
    name: "Rook",
    provider: "email",
    games: 1,
    wins: 0,
    draws: 0,
    losses: 1,
    points: 0,
    win_rate: 0,
  },
];

describe("Leaderboard", () => {
  beforeEach(() => {
    authApi.leaderboard.mockResolvedValue(SAMPLE);
  });

  it("renders ranked players with medals, records and points", async () => {
    render(<Leaderboard />);

    expect(await screen.findByText("Mia")).toBeTruthy();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    // medals for the top 3, "#4" fallback below the podium
    expect(rows[0].textContent).toContain("\u{1F947}"); // gold
    expect(rows[1].textContent).toContain("\u{1F948}"); // silver
    expect(rows[2].textContent).toContain("#4");
    expect(rows[0].textContent).toContain("3W");
    expect(rows[0].textContent).toContain("3.5 pts");
    expect(rows[1].textContent).toContain("Guest-7F3A");
    expect(authApi.leaderboard).toHaveBeenCalledWith(undefined);
  });

  it("requests the selected difficulty filter", async () => {
    const user = userEvent.setup();
    render(<Leaderboard />);
    await screen.findByText("Mia");

    await user.selectOptions(screen.getByRole("combobox"), "hard");

    await waitFor(() => expect(authApi.leaderboard).toHaveBeenCalledWith("hard"));
  });

  it("shows the empty state when nobody has played", async () => {
    authApi.leaderboard.mockResolvedValue([]);
    render(<Leaderboard />);

    expect(await screen.findByText(/be the first name on the board/)).toBeTruthy();
  });

  it("shows an error but keeps the panel usable on failure", async () => {
    authApi.leaderboard.mockRejectedValue(new Error("Could not reach the server."));
    render(<Leaderboard />);

    expect(await screen.findByText("Could not reach the server.")).toBeTruthy();
  });
});

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import GameOverOverlay from "../components/GameOverOverlay.jsx";

describe("GameOverOverlay", () => {
  it("congratulates the player on a win and offers a retry", () => {
    const onRetry = vi.fn();
    render(
      <GameOverOverlay outcome="win" playerColor="w" onRetry={onRetry} onDismiss={() => {}} />
    );

    expect(screen.getByText("Congratulations!")).toBeTruthy();
    expect(screen.getByText(/you played white/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /play again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("encourages the player after a loss with a rematch prompt", () => {
    const onRetry = vi.fn();
    render(
      <GameOverOverlay outcome="loss" playerColor="b" onRetry={onRetry} onDismiss={() => {}} />
    );

    expect(screen.getByText("Better luck next time")).toBeTruthy();
    expect(screen.getByText(/you played black/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("can be dismissed so the final position stays visible", () => {
    const onDismiss = vi.fn();
    render(
      <GameOverOverlay outcome="draw" playerColor="w" onRetry={() => {}} onDismiss={onDismiss} />
    );

    expect(screen.getByText("It's a draw")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /view final board/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("exposes dialog semantics for assistive tech", () => {
    render(
      <GameOverOverlay outcome="win" playerColor="w" onRetry={() => {}} onDismiss={() => {}} />
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("result-title");
  });
});

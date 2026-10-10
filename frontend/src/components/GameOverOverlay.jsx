/**
 * Full-screen result dialog shown when the game ends.
 *
 * - win  -> congratulations + "Play again"
 * - loss -> "Better luck next time" + "Try again"
 * - draw -> neutral message + "Play again"
 *
 * The primary action restarts the game with the same color; the secondary
 * action dismisses the dialog so the final position can be studied.
 */

const MESSAGES = {
  win: {
    icon: "\uD83C\uDFC6", // trophy
    title: "Congratulations!",
    text: "You beat the computer \u2014 want to go again?",
    retry: "Play again",
  },
  loss: {
    icon: "\uD83C\uDF40", // clover
    title: "Better luck next time",
    text: "The computer got you this round. Ready for a rematch?",
    retry: "Try again",
  },
  draw: {
    icon: "\uD83E\uDD1D", // handshake
    title: "It's a draw",
    text: "Neither side could break through. Fancy another?",
    retry: "Play again",
  },
};

export default function GameOverOverlay({ outcome, playerColor, onRetry, onDismiss }) {
  const message = MESSAGES[outcome] ?? MESSAGES.draw;
  const colorName = playerColor === "b" ? "Black" : "White";

  return (
    <div className="result-overlay">
      <div
        className={`result result--${outcome}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="result-title"
      >
        <div className="result__icon" aria-hidden="true">
          {message.icon}
        </div>
        <h2 className="result__title" id="result-title">
          {message.title}
        </h2>
        <p className="result__text">{message.text}</p>
        <p className="result__meta">You played {colorName}.</p>
        <div className="result__actions">
          <button type="button" className="result__retry" onClick={onRetry} autoFocus>
            {message.retry}
          </button>
          <button type="button" onClick={onDismiss}>
            View final board
          </button>
        </div>
      </div>
    </div>
  );
}

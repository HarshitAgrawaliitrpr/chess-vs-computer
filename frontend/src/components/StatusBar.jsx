export default function StatusBar({ status, thinking, error }) {
  const kindClass = `statusbar__badge statusbar__badge--${status.kind}`;

  return (
    <div className="statusbar" role="status" aria-live="polite">
      <span className={kindClass}>{status.kind}</span>
      <span className="statusbar__text">
        {thinking ? "Computer is thinking\u2026" : status.text}
      </span>
      {error ? <span className="statusbar__error">{error}</span> : null}
    </div>
  );
}
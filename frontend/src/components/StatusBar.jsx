export default function StatusBar({ status, thinking, error, preMove, onCancelPreMove }) {
  const kindClass = `statusbar__badge statusbar__badge--${status.kind}`;

  return (
    <div className="statusbar" role="status" aria-live="polite">
      <span className={kindClass}>{status.kind}</span>
      <span className="statusbar__text">
        {thinking ? "Computer is thinking\u2026" : status.text}
      </span>
      {preMove ? (
        <span className="statusbar__premove">
          pre-move {preMove.from} {"\u2192"} {preMove.to}
          <button
            type="button"
            aria-label="Cancel pre-move"
            title="Cancel pre-move"
            onClick={onCancelPreMove}
          >
            {"\u2715"}
          </button>
        </span>
      ) : null}
      {error ? <span className="statusbar__error">{error}</span> : null}
    </div>
  );
}

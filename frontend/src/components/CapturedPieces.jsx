import { PIECE_SYMBOLS } from "../hooks/useChessGame.js";

function PieceRow({ codes, label }) {
  const sorted = [...codes].sort();
  return (
    <div className="captures__row">
      <span className="captures__label">{label}</span>
      <span className="captures__pieces">
        {sorted.length === 0 ? "\u2014" : sorted.map((code, index) => (
          <span key={`${code}-${index}`} className={`captures__piece captures__piece--${code[0]}`}>
            {PIECE_SYMBOLS[code]}
          </span>
        ))}
      </span>
    </div>
  );
}

export default function CapturedPieces({ capturedByWhite, capturedByBlack, advantage }) {
  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Captured</h2>
        {advantage !== 0 ? (
          <span className="captures__advantage">
            {advantage > 0 ? "White" : "Black"} +{Math.abs(advantage)}
          </span>
        ) : null}
      </header>
      <PieceRow codes={capturedByWhite} label="Taken by White" />
      <PieceRow codes={capturedByBlack} label="Taken by Black" />
    </section>
  );
}
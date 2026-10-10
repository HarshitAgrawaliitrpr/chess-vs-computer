import { useMemo } from "react";

/** Format the SAN move list as classic numbered rows: `1. e4 e5`. */
export default function MoveHistory({ moves, pgn }) {
  const rows = useMemo(() => {
    const out = [];
    for (let i = 0; i < moves.length; i += 2) {
      out.push({ number: i / 2 + 1, white: moves[i], black: moves[i + 1] ?? null });
    }
    return out;
  }, [moves]);

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Moves</h2>
        <button
          type="button"
          className="panel__action"
          onClick={() => navigator.clipboard?.writeText(pgn)}
          disabled={!pgn}
          title="Copy PGN"
        >
          Copy PGN
        </button>
      </header>

      {rows.length === 0 ? (
        <p className="panel__empty">No moves yet. Make the first move.</p>
      ) : (
        <ol className="movelist" aria-label="Move history">
          {rows.map((row) => (
            <li key={row.number}>
              <span className="movelist__number">{row.number}.</span>
              <span className="movelist__move">{row.white}</span>
              <span className="movelist__move">{row.black ?? ""}</span>
            </li>
          ))}
        </ol>
      )}

      <details className="pgn">
        <summary>PGN</summary>
        <pre>{pgn || "(empty)"}</pre>
      </details>
    </section>
  );
}
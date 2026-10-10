function formatNodes(nodes) {
  if (nodes >= 1_000_000) return `${(nodes / 1_000_000).toFixed(1)}M`;
  if (nodes >= 1_000) return `${(nodes / 1_000).toFixed(1)}k`;
  return String(nodes);
}

export default function EngineStats({ info, thinking }) {
  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Engine</h2>
        {thinking ? <span className="stats__pulse">searching\u2026</span> : null}
      </header>

      {!info ? (
        <p className="panel__empty">Waiting for the first engine move.</p>
      ) : (
        <dl className="stats">
          <div><dt>Last move</dt><dd>{info.san}</dd></div>
          <div>
            <dt>Evaluation</dt>
            <dd>
              {info.scoreType === "mate"
                ? `mate in ${info.mateIn}`
                : `${(info.score / 100).toFixed(2)} pawns`}
            </dd>
          </div>
          <div><dt>Depth</dt><dd>{info.depth}</dd></div>
          <div><dt>Nodes</dt><dd>{formatNodes(info.nodes)}</dd></div>
          <div><dt>Time</dt><dd>{Math.round(info.timeMs)} ms</dd></div>
          <div><dt>Strength</dt><dd>~{info.elo} Elo</dd></div>
        </dl>
      )}

      {info?.pv?.length ? (
        <p className="stats__pv" title="Principal variation (best line the engine calculated)">
          Line: {info.pv.join(" ")}
        </p>
      ) : null}
    </section>
  );
}
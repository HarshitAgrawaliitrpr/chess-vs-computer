export const DIFFICULTIES = {
  easy: { label: "Easy", hint: "Depth 1 \u00b7 ~750 Elo" },
  medium: { label: "Medium", hint: "Depth 3 \u00b7 ~1250 Elo" },
  hard: { label: "Hard", hint: "Depth 5 \u00b7 ~1650 Elo" },
  master: { label: "Master", hint: "Depth 7 \u00b7 ~2000 Elo" },
};

export default function DifficultySelector({ value, onChange, disabled }) {
  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Difficulty</h2>
      </header>
      <div className="difficulty" role="radiogroup" aria-label="AI difficulty">
        {Object.entries(DIFFICULTIES).map(([key, meta]) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={value === key}
            className={`difficulty__option ${value === key ? "difficulty__option--active" : ""}`}
            onClick={() => onChange(key)}
            disabled={disabled}
          >
            <strong>{meta.label}</strong>
            <small>{meta.hint}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
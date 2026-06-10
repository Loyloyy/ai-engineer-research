// A small segmented pill control (one option active) with a one-line description of the current choice
// shown below — friendlier than a checkbox/dropdown for the new-run form's mode + thoroughness.
export interface SegOption {
  value: string;
  label: string;
  description: string;
}

export default function Segmented({
  options,
  value,
  onChange,
}: {
  options: SegOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  const current = options.find((o) => o.value === value);
  return (
    <div className="segmented-wrap">
      <div className="segmented" role="radiogroup">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={o.value === value}
            className={`seg${o.value === value ? " active" : ""}`}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
      {current && <p className="seg-desc muted small">{current.description}</p>}
    </div>
  );
}

// The guided-flow progress header: Topic → Clarify → Run. Purely presentational — the active step is
// driven by the parent (RunForm phase / live run). Gives the start→clarify→pipeline flow a sense of
// place instead of hard jumps.
const STEPS = ["Topic", "Clarify", "Run"];

export default function Stepper({ step }: { step: number }) {
  return (
    <ol className="stepper">
      {STEPS.map((label, i) => {
        const state = i < step ? "done" : i === step ? "active" : "todo";
        return (
          <li key={label} className={`stepper-step ${state}`}>
            <span className="stepper-dot">{i < step ? "✓" : i + 1}</span>
            <span className="stepper-label">{label}</span>
            {i < STEPS.length - 1 && <span className="stepper-rail" />}
          </li>
        );
      })}
    </ol>
  );
}

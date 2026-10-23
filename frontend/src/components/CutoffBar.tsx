import { monthRange } from "../lib/format";

export const CUTOFFS = monthRange("2022-01", "2024-06");

export function CutoffBar({
  cutoff,
  onChange,
  busy,
  origin,
}: {
  cutoff: string;
  onChange: (c: string) => void;
  busy: boolean;
  origin: "api" | "fixture" | undefined;
}) {
  const idx = Math.max(0, CUTOFFS.indexOf(cutoff));
  const years = CUTOFFS.map((c, i) => (c.endsWith("-01-01") ? i : -1)).filter((i) => i >= 0);

  return (
    <footer className="grid h-11 grid-cols-[180px_1fr_260px] items-center border-t border-line">
      <div className="flex h-full items-center gap-3 border-r border-line px-3">
        <span className="label">Cutoff</span>
        <span className={`text-[13px] ${busy ? "text-muted" : "text-accent"}`}>{cutoff}</span>
      </div>
      <div className="relative px-4">
        <input
          type="range"
          className="cutoff"
          min={0}
          max={CUTOFFS.length - 1}
          step={1}
          value={idx}
          onChange={(e) => onChange(CUTOFFS[Number(e.target.value)])}
          aria-label="Historical cutoff date"
        />
        <div className="pointer-events-none absolute inset-x-4 top-[26px] h-3">
          {years.map((i) => (
            <span
              key={i}
              className="absolute -translate-x-1/2 text-[9px] text-faint"
              style={{ left: `${(i / (CUTOFFS.length - 1)) * 100}%` }}
            >
              {CUTOFFS[i].slice(0, 4)}
            </span>
          ))}
        </div>
      </div>
      <div className="flex h-full items-center justify-end gap-3 border-l border-line px-3">
        <span className="label">
          {busy ? "Running agents" : origin === "fixture" ? "Fixture data" : "Bedrock"}
        </span>
        <span className={`inline-block h-[5px] w-[5px] ${busy ? "animate-pulse bg-accent" : origin === "api" ? "bg-up" : "bg-faint"}`} />
      </div>
    </footer>
  );
}

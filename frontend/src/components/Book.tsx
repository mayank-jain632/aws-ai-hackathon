import type { Weight } from "../types";
import { pctPlain } from "../lib/format";

export function Book({
  weights,
  selected,
  onSelect,
}: {
  weights: Weight[];
  selected: string | null;
  onSelect: (ticker: string) => void;
}) {
  const max = Math.max(...weights.map((w) => w.weight));
  const sorted = [...weights].sort((a, b) => b.weight - a.weight);

  return (
    <section className="flex h-full flex-col border-r border-line">
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
        <span className="label">Book</span>
        <span className="label">Target weights · long only · monthly rebalance</span>
      </header>
      <div className="grid grid-cols-[56px_120px_1fr] border-b border-line px-3 py-1">
        <span className="label">Ticker</span>
        <span className="label">Weight</span>
        <span className="label">Portfolio manager rationale</span>
      </div>
      <div className="scroll flex-1">
        {sorted.map((w) => {
          const active = selected === w.ticker;
          return (
            <button
              key={w.ticker}
              type="button"
              onClick={() => onSelect(w.ticker)}
              className={`grid w-full grid-cols-[56px_120px_1fr] items-start border-b border-line px-3 py-2.5 text-left transition-colors ${
                active ? "bg-panel" : "hover:bg-panel"
              }`}
            >
              <span className={`text-[13px] ${active ? "text-accent" : "text-ink"}`}>{w.ticker}</span>
              <span className="flex items-center gap-2 pr-4">
                <span className="w-9 text-[13px] text-ink">{pctPlain(w.weight)}</span>
                <span className="relative inline-block h-px flex-1 bg-line">
                  <span
                    className={`absolute left-0 top-0 h-px ${active ? "bg-accent" : "bg-ink"}`}
                    style={{ width: `${(w.weight / max) * 100}%` }}
                  />
                </span>
              </span>
              <span className="min-w-0">
                <span className="block text-[11.5px] leading-snug text-ink">{w.rationale}</span>
                <span className="mt-1 block text-[11px] leading-snug text-muted">
                  <span className="text-faint">Changes my mind · </span>
                  {w.changes_my_mind}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

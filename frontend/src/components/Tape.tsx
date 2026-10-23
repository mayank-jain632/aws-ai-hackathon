import type { TapeState } from "../lib/useTape";
import { pct } from "../lib/format";

export function Tape({ tape, tickers }: { tape: TapeState; tickers: string[] }) {
  const items = tickers.map((t) => {
    const tick = tape.ticks[t];
    const up = tick.change_pct >= 0;
    return (
      <span key={t} className="inline-flex items-baseline gap-2 pr-10">
        <span className="text-ink">{t}</span>
        <span className="text-ink">{tick.price.toFixed(2)}</span>
        <span className={tape.status === "live" ? (up ? "text-up" : "text-down") : "text-faint"}>
          {tape.status === "live" ? pct(tick.change_pct) : "last close"}
        </span>
      </span>
    );
  });

  return (
    <div className="flex h-7 items-center border-b border-line">
      <div className="flex h-full shrink-0 items-center gap-2 border-r border-line px-3">
        <span
          className={`inline-block h-[5px] w-[5px] ${
            tape.status === "live" ? "bg-accent" : "bg-faint"
          }`}
        />
        <span className="label">{tape.status === "live" ? "Live" : "Tape off"}</span>
      </div>
      <div className="relative h-full flex-1 overflow-hidden">
        <div className="tape-track absolute left-0 top-0 flex h-full items-center pl-4">
          {items}
          {items}
        </div>
      </div>
    </div>
  );
}

import { useCallback, useState } from "react";
import { Tape } from "./components/Tape";
import { Analysts } from "./components/Analysts";
import { Book } from "./components/Book";
import { Performance } from "./components/Performance";
import { CutoffBar } from "./components/CutoffBar";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { UNIVERSE, useRun } from "./lib/useRun";
import { useTape } from "./lib/useTape";

export default function App() {
  const [cutoff, setCutoff] = useState("2023-01-01");
  const [selected, setSelected] = useState<string | null>(null);
  const run = useRun(cutoff);
  const tape = useTape(UNIVERSE);
  const close = useCallback(() => setSelected(null), []);

  const data = run.data?.data;

  return (
    <div className="grid h-full grid-rows-[28px_44px_1fr_44px] overflow-hidden">
      <Tape tape={tape} tickers={UNIVERSE} />

      <header className="grid grid-cols-[1fr_auto] items-center border-b border-line px-3">
        <div className="flex items-baseline gap-4">
          <h1 className="serif text-[22px] leading-none text-ink">The Desk</h1>
          <span className="text-[11px] text-muted">
            Five analyst agents, one portfolio manager, one cutoff date. A historical experiment, not advice.
          </span>
        </div>
        <dl className="flex items-baseline gap-6 text-[11px]">
          <div className="flex gap-2">
            <dt className="label">Universe</dt>
            <dd className="text-ink">{UNIVERSE.join(" ")}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="label">Baseline</dt>
            <dd className="text-ink">Equal weight</dd>
          </div>
          <div className="flex gap-2">
            <dt className="label">Rebalance</dt>
            <dd className="text-ink">Monthly</dd>
          </div>
        </dl>
      </header>

      {data ? (
        <main className="grid min-h-0 grid-cols-[300px_1fr_440px]">
          <Analysts memos={data.memos} />
          <Book weights={data.weights} selected={selected} onSelect={setSelected} />
          <Performance equity={data.equity} metrics={data.metrics} cutoff={data.cutoff} />
        </main>
      ) : (
        <main className="flex items-center justify-center">
          <span className="label">Loading</span>
        </main>
      )}

      <CutoffBar cutoff={cutoff} onChange={setCutoff} busy={run.isFetching} origin={run.data?.origin} />

      {data && <EvidenceDrawer run={data} ticker={selected} onClose={close} />}
    </div>
  );
}

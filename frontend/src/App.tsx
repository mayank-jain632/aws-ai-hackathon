import { useState } from "react";
import { Results } from "./components/Results";
import { Allocation } from "./components/Allocation";
import { Memos } from "./components/Memos";
import { UNIVERSE, useRun } from "./lib/useRun";
import { monthRange } from "./lib/format";

const CUTOFFS = monthRange("2022-01", "2024-06");

export default function App() {
  const [cutoff, setCutoff] = useState("2023-01-01");
  const run = useRun(cutoff);
  const data = run.data?.data;

  return (
    <div className="mx-auto max-w-[860px] px-5 py-10">
      <header className="border-b border-ink pb-4">
        <h1 className="text-[26px] leading-tight">Multi-signal portfolio experiment</h1>
        <p className="mt-2 text-muted">
          Five analyst agents read price, fundamentals, macro, sentiment and geopolitical data
          dated on or before a cutoff. A portfolio-manager agent sets weights. The result is
          backtested forward against an equal-weight baseline. Historical experiment, not advice.
        </p>
        <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-1 text-[14px]">
          <dt className="text-muted">Universe</dt>
          <dd className="num">{UNIVERSE.join("  ")}</dd>
          <dt className="text-muted">Cutoff</dt>
          <dd>
            <select value={cutoff} onChange={(e) => setCutoff(e.target.value)} className="num">
              {CUTOFFS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <span className="ml-3 text-[13px] text-faint">
              {run.isFetching ? "running agents…" : run.data?.origin === "fixture" ? "fixture data" : ""}
            </span>
          </dd>
          <dt className="text-muted">Baseline</dt>
          <dd>Equal weight, monthly rebalance, no costs</dd>
          <dt className="text-muted">Window</dt>
          <dd className="num">{cutoff} to 2025-06-30</dd>
        </dl>
      </header>

      {data ? (
        <>
          <Results equity={data.equity} metrics={data.metrics} />
          <Allocation weights={data.weights} />
          <Memos memos={data.memos} sources={data.sources} />
        </>
      ) : (
        <p className="mt-8 text-muted">Loading…</p>
      )}
    </div>
  );
}

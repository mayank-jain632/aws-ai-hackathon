import type { Weight } from "../types";
import { pctPlain } from "../lib/format";

export function Allocation({ weights }: { weights: Weight[] }) {
  const sorted = [...weights].sort((a, b) => b.weight - a.weight);
  return (
    <section className="mt-10">
      <h2 className="text-[18px]">Allocation</h2>
      <p className="mb-3 text-[13px] text-muted">Target weights set by the portfolio-manager agent, with its reasoning and the condition that would change the position.</p>
      <table>
        <thead>
          <tr>
            <th className="w-[72px]">Ticker</th>
            <th className="w-[72px]">Weight</th>
            <th>Rationale</th>
            <th className="w-[34%]">Changes the position if</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((w) => (
            <tr key={w.ticker}>
              <td className="num">{w.ticker}</td>
              <td className="num">{pctPlain(w.weight)}</td>
              <td className="pr-4 text-[14px]">{w.rationale}</td>
              <td className="text-[14px] text-muted">{w.changes_my_mind}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

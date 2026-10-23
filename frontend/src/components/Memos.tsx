import type { Memo, Source } from "../types";
import { ANALYST_LABEL, KIND_LABEL } from "../lib/format";

export function Memos({ memos, sources }: { memos: Memo[]; sources: Source[] }) {
  const byId = new Map(sources.map((s) => [s.id, s]));
  return (
    <section className="mt-10">
      <h2 className="text-[18px]">Analyst memos</h2>
      <p className="mb-3 text-[13px] text-muted">Each memo is dated at the cutoff and cites only sources available by then.</p>
      {memos.map((m) => {
        const cited = [...new Set(m.views.flatMap((v) => v.sources))]
          .map((id) => byId.get(id))
          .filter((s): s is Source => Boolean(s));
        return (
          <article key={m.analyst} className="border-t border-line py-5">
            <div className="flex items-baseline justify-between">
              <h3 className="text-[16px] font-medium">{ANALYST_LABEL[m.analyst]}</h3>
              <span className="num text-[12px] text-faint">{m.date}</span>
            </div>
            <p className="mt-1 font-medium">{m.headline}</p>
            <p className="mt-1 text-[14px]">{m.body}</p>
            <table className="mt-3">
              <thead>
                <tr>
                  <th className="w-[72px]">Ticker</th>
                  <th className="w-[80px]">Stance</th>
                  <th className="w-[90px]">Confidence</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {m.views.map((v) => (
                  <tr key={v.ticker}>
                    <td className="num">{v.ticker}</td>
                    <td className={`text-[14px] ${v.stance === "long" ? "text-up" : v.stance === "avoid" ? "text-down" : "text-muted"}`}>{v.stance}</td>
                    <td className="num">{v.confidence.toFixed(2)}</td>
                    <td className="text-[14px] text-muted">{v.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cited.length > 0 && (
              <ol className="mt-3 list-decimal pl-5 text-[13px] text-muted">
                {cited.map((s) => (
                  <li key={s.id}>
                    <span className="text-faint">{KIND_LABEL[s.kind]}</span> {s.title}, {s.date}.{" "}
                    {s.url && (
                      <a href={s.url} target="_blank" rel="noreferrer" className="underline">
                        link
                      </a>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </article>
        );
      })}
    </section>
  );
}

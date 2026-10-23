import type { Memo } from "../types";
import { ANALYST_LABEL, STANCE_GLYPH } from "../lib/format";

function Confidence({ value }: { value: number }) {
  return (
    <span className="relative inline-block h-px w-10 bg-line align-middle">
      <span
        className="absolute left-0 top-0 h-px bg-ink"
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </span>
  );
}

export function Analysts({ memos }: { memos: Memo[] }) {
  return (
    <section className="flex h-full flex-col border-r border-line">
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
        <span className="label">Analysts</span>
        <span className="label">{memos.length} memos</span>
      </header>
      <div className="scroll flex-1">
        {memos.map((m) => (
          <article key={m.analyst} className="border-b border-line px-3 py-3">
            <div className="flex items-baseline justify-between">
              <span className="label text-ink">{ANALYST_LABEL[m.analyst]}</span>
              <span className="text-[10px] text-faint">{m.date}</span>
            </div>
            <h3 className="serif mt-1 text-[15px] leading-tight text-ink">{m.headline}</h3>
            <p className="mt-1.5 text-[11px] leading-snug text-muted">{m.body}</p>
            <ul className="mt-2 space-y-[3px]">
              {m.views.map((v) => (
                <li key={v.ticker} className="flex items-center gap-2 text-[11px]">
                  <span
                    className={`w-2 text-center ${
                      v.stance === "long" ? "text-up" : v.stance === "avoid" ? "text-down" : "text-faint"
                    }`}
                  >
                    {STANCE_GLYPH[v.stance]}
                  </span>
                  <span className="w-11 text-ink">{v.ticker}</span>
                  <Confidence value={v.confidence} />
                  <span className="truncate text-muted">{v.note}</span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

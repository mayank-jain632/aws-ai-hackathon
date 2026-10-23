import { useEffect } from "react";
import type { RunResponse } from "../types";
import { ANALYST_LABEL, KIND_LABEL, STANCE_GLYPH, pctPlain } from "../lib/format";

export function EvidenceDrawer({
  run,
  ticker,
  onClose,
}: {
  run: RunResponse;
  ticker: string | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!ticker) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ticker, onClose]);

  if (!ticker) return null;
  const w = run.weights.find((x) => x.ticker === ticker);
  if (!w) return null;

  const views = run.memos
    .map((m) => ({ analyst: m.analyst, view: m.views.find((v) => v.ticker === ticker) }))
    .filter((x) => x.view);
  const sourceIds = new Set(views.flatMap((x) => x.view!.sources));
  const sources = run.sources.filter((s) => sourceIds.has(s.id));
  const influence = Object.entries(w.analyst_influence).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-20 flex w-[480px] flex-col border-l border-line bg-bg">
        <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
          <span className="label">Evidence · {ticker}</span>
          <button type="button" onClick={onClose} className="label hover:text-ink">
            Esc
          </button>
        </header>
        <div className="scroll flex-1 px-3 py-3">
          <div className="flex items-baseline gap-3">
            <span className="serif text-[28px] leading-none text-ink">{ticker}</span>
            <span className="text-[13px] text-accent">{pctPlain(w.weight)}</span>
          </div>
          <p className="mt-2 text-[11.5px] leading-snug text-ink">{w.rationale}</p>
          <p className="mt-1 text-[11px] leading-snug text-muted">
            <span className="text-faint">Changes my mind · </span>
            {w.changes_my_mind}
          </p>

          <h4 className="label mt-5 border-b border-line pb-1">How the PM weighed the desk</h4>
          <ul className="mt-2 space-y-1">
            {influence.map(([a, v]) => (
              <li key={a} className="grid grid-cols-[96px_1fr_36px] items-center gap-2 text-[11px]">
                <span className="text-ink">{ANALYST_LABEL[a]}</span>
                <span className="relative h-px bg-line">
                  <span className="absolute left-0 top-0 h-px bg-accent" style={{ width: `${v * 100}%` }} />
                </span>
                <span className="text-right text-muted">{pctPlain(v)}</span>
              </li>
            ))}
          </ul>

          <h4 className="label mt-5 border-b border-line pb-1">Analyst views</h4>
          <ul className="mt-2 space-y-2">
            {views.map(({ analyst, view }) => (
              <li key={analyst} className="text-[11px]">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 text-center ${
                      view!.stance === "long" ? "text-up" : view!.stance === "avoid" ? "text-down" : "text-faint"
                    }`}
                  >
                    {STANCE_GLYPH[view!.stance]}
                  </span>
                  <span className="text-ink">{ANALYST_LABEL[analyst]}</span>
                  <span className="text-faint">conf {view!.confidence.toFixed(2)}</span>
                </div>
                <p className="ml-4 text-muted">{view!.note}</p>
              </li>
            ))}
          </ul>

          <h4 className="label mt-5 border-b border-line pb-1">Sources cited · all dated on or before {run.cutoff}</h4>
          <ol className="mt-2 space-y-2.5">
            {sources.map((s, i) => (
              <li key={s.id} className="grid grid-cols-[20px_1fr] gap-1 text-[11px]">
                <span className="text-faint">{i + 1}.</span>
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-[9px] tracking-[0.12em] text-accent">{KIND_LABEL[s.kind]}</span>
                    <span className="text-ink">{s.title}</span>
                  </div>
                  <div className="text-[10px] text-faint">{s.date}</div>
                  <p className="mt-0.5 leading-snug text-muted">{s.excerpt}</p>
                  {s.url && (
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-[10px] text-faint underline decoration-line hover:text-ink">
                      source
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </>
  );
}

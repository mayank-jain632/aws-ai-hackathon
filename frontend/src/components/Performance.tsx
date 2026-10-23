import { useEffect, useRef } from "react";
import { createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { Equity, Metrics } from "../types";
import { num, pct } from "../lib/format";

const MUTED = "#8a8782";
const FAINT = "#4a4844";
const ACCENT = "#d9a441";
const LINE = "#232528";

function toSeries(dates: string[], values: number[]) {
  return dates.map((d, i) => ({
    time: (Date.parse(d) / 1000) as UTCTimestamp,
    value: values[i],
  }));
}

function Curve({ equity }: { equity: Equity }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { color: "transparent" },
        textColor: MUTED,
        fontFamily: '"IBM Plex Mono", monospace',
        fontSize: 10,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { borderColor: LINE, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: LINE, timeVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: FAINT, width: 1, style: 3, labelBackgroundColor: "#0b0c0e" },
        horzLine: { color: FAINT, width: 1, style: 3, labelBackgroundColor: "#0b0c0e" },
      },
      handleScroll: false,
      handleScale: false,
      autoSize: true,
    });
    chartRef.current = chart;

    const mk = (color: string, width: 1 | 2, title: string) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        title,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(2) },
      });

    const spy = mk(FAINT, 1, "SPY");
    const ew = mk(MUTED, 1, "EW");
    const pf = mk(ACCENT, 2, "DESK");

    spy.setData(toSeries(equity.dates, equity.spy));
    ew.setData(toSeries(equity.dates, equity.equal_weight));
    pf.setData(toSeries(equity.dates, equity.portfolio));
    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [equity]);

  return <div ref={ref} className="h-full w-full" />;
}

function Row({ label, m, strong }: { label: string; m: Metrics; strong?: boolean }) {
  const c = strong ? "text-ink" : "text-muted";
  return (
    <div className="grid grid-cols-[72px_repeat(4,1fr)] items-baseline px-3 py-1.5">
      <span className={`text-[11px] ${strong ? "text-accent" : "text-faint"}`}>{label}</span>
      <span className={`text-[13px] ${m.total_return >= 0 ? "text-up" : "text-down"}`}>{pct(m.total_return)}</span>
      <span className={`text-[13px] ${c}`}>{pct(m.cagr)}</span>
      <span className={`text-[13px] ${m.max_drawdown < 0 ? "text-down" : c}`}>{pct(m.max_drawdown)}</span>
      <span className={`text-[13px] ${c}`}>{num(m.sharpe)}</span>
    </div>
  );
}

export function Performance({
  equity,
  metrics,
  cutoff,
}: {
  equity: Equity;
  metrics: { portfolio: Metrics; baseline: Metrics };
  cutoff: string;
}) {
  const end = equity.dates[equity.dates.length - 1];
  return (
    <section className="flex h-full flex-col">
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
        <span className="label">Performance</span>
        <span className="label">
          {cutoff} → {end} · growth of 1.00
        </span>
      </header>
      <div className="flex items-center gap-4 border-b border-line px-3 py-1.5 text-[10px]">
        <span className="flex items-center gap-1.5"><i className="inline-block h-px w-4" style={{ background: ACCENT }} />Desk</span>
        <span className="flex items-center gap-1.5 text-muted"><i className="inline-block h-px w-4 bg-muted" />Equal weight</span>
        <span className="flex items-center gap-1.5 text-muted"><i className="inline-block h-px w-4 bg-faint" />SPY</span>
      </div>
      <div className="min-h-0 flex-1 p-2">
        <Curve equity={equity} />
      </div>
      <div className="shrink-0 border-t border-line">
        <div className="grid grid-cols-[72px_repeat(4,1fr)] border-b border-line px-3 py-1">
          <span className="label">&nbsp;</span>
          <span className="label">Return</span>
          <span className="label">CAGR</span>
          <span className="label">Max DD</span>
          <span className="label">Sharpe</span>
        </div>
        <Row label="Desk" m={metrics.portfolio} strong />
        <Row label="Baseline" m={metrics.baseline} />
      </div>
    </section>
  );
}

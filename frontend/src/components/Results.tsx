import { useEffect, useRef } from "react";
import { createChart, LineSeries, type UTCTimestamp } from "lightweight-charts";
import type { Equity, Metrics } from "../types";
import { num, pct } from "../lib/format";

function toSeries(dates: string[], values: number[]) {
  return dates.map((d, i) => ({ time: (Date.parse(d) / 1000) as UTCTimestamp, value: values[i] }));
}

function Curve({ equity }: { equity: Equity }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { color: "transparent" },
        textColor: "#6b6b6b",
        fontFamily: '"IBM Plex Mono", monospace',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#f0f0f0" } },
      rightPriceScale: { borderColor: "#e4e4e4" },
      timeScale: { borderColor: "#e4e4e4", fixLeftEdge: true, fixRightEdge: true },
      handleScroll: false,
      handleScale: false,
      autoSize: true,
    });
    const mk = (color: string, width: 1 | 2, title: string) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        title,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(2) },
      });
    mk("#c4c4c4", 1, "SPY").setData(toSeries(equity.dates, equity.spy));
    mk("#8a8a8a", 1, "Equal weight").setData(toSeries(equity.dates, equity.equal_weight));
    mk("#1a1a1a", 2, "Portfolio").setData(toSeries(equity.dates, equity.portfolio));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [equity]);

  return <div ref={ref} className="h-[300px] w-full" />;
}

function Row({ label, m }: { label: string; m: Metrics }) {
  return (
    <tr>
      <td>{label}</td>
      <td className={`num ${m.total_return >= 0 ? "text-up" : "text-down"}`}>{pct(m.total_return)}</td>
      <td className="num">{pct(m.cagr)}</td>
      <td className="num text-down">{pct(m.max_drawdown)}</td>
      <td className="num">{num(m.sharpe)}</td>
    </tr>
  );
}

export function Results({ equity, metrics }: { equity: Equity; metrics: { portfolio: Metrics; baseline: Metrics } }) {
  return (
    <section className="mt-10">
      <h2 className="text-[18px]">Results</h2>
      <p className="mb-3 text-[13px] text-muted">Growth of 1.00 from the cutoff. Portfolio in black, equal weight in grey, SPY in light grey.</p>
      <Curve equity={equity} />
      <table className="mt-4">
        <thead>
          <tr>
            <th>&nbsp;</th>
            <th>Total return</th>
            <th>CAGR</th>
            <th>Max drawdown</th>
            <th>Sharpe</th>
          </tr>
        </thead>
        <tbody>
          <Row label="Portfolio" m={metrics.portfolio} />
          <Row label="Equal weight" m={metrics.baseline} />
        </tbody>
      </table>
    </section>
  );
}

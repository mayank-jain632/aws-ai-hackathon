import { useEffect, useRef, useState } from "react";
import type { TapeTick } from "../types";

export const TAPE_SYMBOLS: Record<string, string> = {
  AAPL: "NASDAQ:AAPL",
  MSFT: "NASDAQ:MSFT",
  NVDA: "NASDAQ:NVDA",
  AMZN: "NASDAQ:AMZN",
  GOOGL: "NASDAQ:GOOGL",
  JPM: "NYSE:JPM",
  XOM: "NYSE:XOM",
  UNH: "NYSE:UNH",
  PG: "NYSE:PG",
  CAT: "NYSE:CAT",
};

// Fallback when the sidecar is down. Lane B can replace these with real last closes.
const LAST_CLOSE: Record<string, number> = {
  AAPL: 231.4, MSFT: 412.1, NVDA: 138.2, AMZN: 186.5, GOOGL: 165.3,
  JPM: 221.7, XOM: 118.9, UNH: 352.4, PG: 168.2, CAT: 378.6,
};

export type TapeState = {
  status: "live" | "offline";
  ticks: Record<string, TapeTick>;
};

const WS_URL = "ws://localhost:8765/tape";

export function useTape(tickers: string[]): TapeState {
  const [status, setStatus] = useState<"live" | "offline">("offline");
  const [ticks, setTicks] = useState<Record<string, TapeTick>>(() => {
    const init: Record<string, TapeTick> = {};
    for (const t of tickers) {
      init[t] = { symbol: TAPE_SYMBOLS[t] ?? t, price: LAST_CLOSE[t] ?? 0, change_pct: 0, ts: 0 };
    }
    return init;
  });
  const retry = useRef(1000);

  // Seed the fallback from the backend's last committed close, if it is up.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/last-close")
      .then((r) => (r.ok ? r.json() : null))
      .then((rows: Record<string, { close: number; change_pct: number }> | null) => {
        if (!rows || cancelled) return;
        setTicks((prev) => {
          const next = { ...prev };
          for (const [t, row] of Object.entries(rows)) {
            if (next[t] && next[t].ts === 0) {
              next[t] = { ...next[t], price: row.close, change_pct: row.change_pct / 100 };
            }
          }
          return next;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        schedule();
        return;
      }
      ws.onopen = () => {
        retry.current = 1000;
        setStatus("live");
      };
      ws.onmessage = (ev) => {
        try {
          const tick = JSON.parse(ev.data) as TapeTick;
          const ticker = Object.keys(TAPE_SYMBOLS).find((k) => TAPE_SYMBOLS[k] === tick.symbol);
          if (!ticker) return;
          setTicks((prev) => ({ ...prev, [ticker]: tick }));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setStatus("offline");
        schedule();
      };
      ws.onerror = () => ws?.close();
    };

    const schedule = () => {
      if (closed) return;
      timer = window.setTimeout(connect, retry.current);
      retry.current = Math.min(retry.current * 2, 15000);
    };

    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { status, ticks };
}

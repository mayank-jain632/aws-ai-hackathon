// The contract between the UI, the data/backtest lane and the agents lane.
// Keep in sync with api/schema.py.

export type Stance = "long" | "neutral" | "avoid";
export type Analyst = "technical" | "fundamentals" | "macro" | "sentiment" | "geopolitics";
export type SourceKind = "sec" | "fred" | "gdelt" | "price";
export type Baseline = "equal_weight" | "spy";

export interface RunRequest {
  universe: string[];
  cutoff: string; // ISO date
  baseline: Baseline;
}

export interface Source {
  id: string;
  kind: SourceKind;
  title: string;
  date: string; // ISO date, <= cutoff
  url?: string;
  excerpt: string;
}

export interface View {
  ticker: string;
  stance: Stance;
  confidence: number; // 0..1
  note: string;
  sources: string[]; // Source ids
}

export interface Memo {
  analyst: Analyst;
  date: string;
  headline: string;
  body: string;
  views: View[];
}

export interface Weight {
  ticker: string;
  weight: number; // 0..1, all weights sum to 1
  rationale: string;
  changes_my_mind: string;
  analyst_influence: Partial<Record<Analyst, number>>;
}

export interface Equity {
  dates: string[];
  portfolio: number[];
  equal_weight: number[];
  spy: number[];
}

export interface Metrics {
  total_return: number;
  cagr: number;
  max_drawdown: number;
  sharpe: number;
}

export interface RunResponse {
  universe: string[];
  cutoff: string;
  baseline: Baseline;
  sources: Source[];
  memos: Memo[];
  weights: Weight[];
  equity: Equity;
  metrics: { portfolio: Metrics; baseline: Metrics };
}

// Live tape message from the TradingView sidecar (ws://localhost:8765/tape)
export interface TapeTick {
  symbol: string; // e.g. "NASDAQ:AAPL"
  price: number;
  change_pct: number;
  ts: number; // unix seconds
}

export const pct = (x: number, digits = 1) =>
  `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(digits)}%`;

export const pctPlain = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;

export const num = (x: number, digits = 2) => x.toFixed(digits);

export const ANALYST_LABEL: Record<string, string> = {
  technical: "Technical",
  fundamentals: "Fundamentals",
  macro: "Macro",
  sentiment: "Sentiment",
  geopolitics: "Geopolitics",
};

export const STANCE_GLYPH: Record<string, string> = {
  long: "▲", // ▲
  neutral: "–", // –
  avoid: "▼", // ▼
};

export const KIND_LABEL: Record<string, string> = {
  sec: "SEC",
  fred: "FRED",
  gdelt: "GDELT",
  price: "PRICE",
};

/** Months between two YYYY-MM dates, inclusive, as ISO first-of-month strings. */
export function monthRange(from: string, to: string): string[] {
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  const out: string[] = [];
  for (let y = fy, m = fm; y < ty || (y === ty && m <= tm); ) {
    out.push(`${y}-${String(m).padStart(2, "0")}-01`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

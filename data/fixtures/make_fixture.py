"""Builds data/fixtures/run_2023-01-01.json, a hand-authored RunResponse for UI work.

Memos, weights and sources are written by hand below. The equity curves are synthetic
(seeded random walks with the right rough shape) so the chart has something to draw
until Lane B's real backtest replaces this file.

Run:  python -I data/fixtures/make_fixture.py
"""

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

CUTOFF = "2023-01-01"
END = date(2025, 6, 30)
UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "UNH", "PG", "CAT"]

SOURCES = [
    {"id": "sec-aapl-10k-2022", "kind": "sec", "title": "Apple 10-K FY2022, Item 7 MD&A",
     "date": "2022-10-28", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K",
     "excerpt": "Net sales $394.3B, +8% y/y. Services revenue $78.1B, +14%. Gross margin 43.3%."},
    {"id": "sec-msft-10q-q1fy23", "kind": "sec", "title": "Microsoft 10-Q, quarter ended Sep 30 2022",
     "date": "2022-10-25", "excerpt": "Azure and other cloud services revenue grew 35%. Operating income $21.5B."},
    {"id": "sec-nvda-10q-q3fy23", "kind": "sec", "title": "NVIDIA 10-Q, quarter ended Oct 30 2022",
     "date": "2022-11-22", "excerpt": "Revenue $5.93B, down 17% y/y. Data Center $3.83B, +31% y/y. Gaming down 51%."},
    {"id": "sec-amzn-10q-q3-2022", "kind": "sec", "title": "Amazon 10-Q, quarter ended Sep 30 2022",
     "date": "2022-10-28", "excerpt": "AWS net sales $20.5B, +27%. Operating cash flow TTM $39.7B, down from $54.7B."},
    {"id": "sec-xom-10q-q3-2022", "kind": "sec", "title": "Exxon Mobil 10-Q, quarter ended Sep 30 2022",
     "date": "2022-11-02", "excerpt": "Earnings $19.7B for the quarter. Net debt-to-capital 12%, lowest in a decade."},
    {"id": "sec-unh-10q-q3-2022", "kind": "sec", "title": "UnitedHealth 10-Q, quarter ended Sep 30 2022",
     "date": "2022-10-14", "excerpt": "Revenues $80.9B, +12%. Medical care ratio 81.6%. 2023 outlook reaffirmed."},
    {"id": "sec-jpm-10q-q3-2022", "kind": "sec", "title": "JPMorgan 10-Q, quarter ended Sep 30 2022",
     "date": "2022-11-01", "excerpt": "Net interest income $17.6B, +34%. CET1 ratio 12.5%. Credit reserve build $808M."},
    {"id": "fred-fedfunds-2022-12", "kind": "fred", "title": "FRED FEDFUNDS, December 2022",
     "date": "2022-12-14", "url": "https://fred.stlouisfed.org/series/FEDFUNDS",
     "excerpt": "Target range raised 50bp to 4.25-4.50%. Dot plot median for 2023: 5.1%."},
    {"id": "fred-cpi-2022-11", "kind": "fred", "title": "FRED CPIAUCSL, November 2022 release",
     "date": "2022-12-13", "url": "https://fred.stlouisfed.org/series/CPIAUCSL",
     "excerpt": "Headline CPI 7.1% y/y, down from 7.7%. Core 6.0%. Fifth consecutive deceleration."},
    {"id": "fred-t10y2y-2022-12", "kind": "fred", "title": "FRED T10Y2Y, 2s10s spread",
     "date": "2022-12-30", "url": "https://fred.stlouisfed.org/series/T10Y2Y",
     "excerpt": "Spread at -55bp, deepest inversion since 1981. Inverted since July 2022."},
    {"id": "fred-unrate-2022-12", "kind": "fred", "title": "FRED UNRATE, December 2022",
     "date": "2022-12-02", "excerpt": "Unemployment 3.7%. Payrolls +263K. Average hourly earnings +5.1% y/y."},
    {"id": "gdelt-ukraine-energy", "kind": "gdelt", "title": "GDELT GKG: Ukraine war, European energy, Q4 2022",
     "date": "2022-12-28", "excerpt": "Event volume on energy sanctions +40% q/q. Average tone -4.2. EU price cap on Russian crude effective Dec 5."},
    {"id": "gdelt-china-reopen", "kind": "gdelt", "title": "GDELT GKG: China zero-COVID exit",
     "date": "2022-12-26", "excerpt": "Beijing drops inbound quarantine effective Jan 8. Tone shifts from -3.1 to +0.8 over two weeks."},
    {"id": "gdelt-chips-export", "kind": "gdelt", "title": "GDELT GKG: US export controls on advanced chips to China",
     "date": "2022-10-07", "excerpt": "BIS rule restricts A100/H100-class sales. Coverage tone -2.6, sustained through December."},
    {"id": "gdelt-apple-foxconn", "kind": "gdelt", "title": "GDELT GKG: Zhengzhou Foxconn disruption",
     "date": "2022-11-30", "excerpt": "Worker protests and lockdown at the largest iPhone plant. Tone -5.4. Shipment cut estimates widely reported."},
    {"id": "price-nvda-200d", "kind": "price", "title": "NVDA close vs 200-day moving average",
     "date": "2022-12-30", "excerpt": "Close $146.14, 200dma $167.90. Below trend since April. 50dma turned up in December."},
    {"id": "price-aapl-rsi", "kind": "price", "title": "AAPL 14-day RSI and drawdown",
     "date": "2022-12-30", "excerpt": "RSI 31. Down 31% from the Jan 2022 high. Volume rising on down days."},
    {"id": "price-xom-trend", "kind": "price", "title": "XOM trend and relative strength",
     "date": "2022-12-30", "excerpt": "Above 50dma and 200dma all year. +80% in 2022. Relative strength vs SPY at 5-year high."},
    {"id": "price-cat-breakout", "kind": "price", "title": "CAT 52-week high",
     "date": "2022-12-30", "excerpt": "New 52-week high on Dec 1. Held above $230 on pullback. Industrials outperforming since October."},
    {"id": "price-spy-regime", "kind": "price", "title": "SPY drawdown and realised volatility",
     "date": "2022-12-30", "excerpt": "SPY -19.4% for 2022. 30-day realised vol 20%. Second test of the October low held."},
]

MEMOS = [
    {
        "analyst": "technical", "date": "2022-12-30",
        "headline": "Energy and industrials lead; mega-cap tech still below trend",
        "body": "Breadth has improved since the October low but leadership sits in XOM and CAT, both making highs. AAPL and NVDA remain under their 200-day averages. I am not willing to fight the trend in tech until price reclaims it, but the oversold readings argue against being short.",
        "views": [
            {"ticker": "XOM", "stance": "long", "confidence": 0.8, "note": "Strongest trend in the universe.", "sources": ["price-xom-trend"]},
            {"ticker": "CAT", "stance": "long", "confidence": 0.7, "note": "Clean breakout, held on pullback.", "sources": ["price-cat-breakout"]},
            {"ticker": "NVDA", "stance": "neutral", "confidence": 0.5, "note": "Below 200dma, 50dma turning up. Watch $170.", "sources": ["price-nvda-200d"]},
            {"ticker": "AAPL", "stance": "neutral", "confidence": 0.5, "note": "Oversold, not yet in an uptrend.", "sources": ["price-aapl-rsi"]},
            {"ticker": "AMZN", "stance": "avoid", "confidence": 0.6, "note": "Lower highs since August.", "sources": ["price-spy-regime"]},
        ],
    },
    {
        "analyst": "fundamentals", "date": "2022-12-30",
        "headline": "Cash generators at a discount; cloud still compounding",
        "body": "Apple, Microsoft and UnitedHealth are compounding earnings through a slowing economy. NVIDIA's gaming collapse masks a data-center line growing 31% off a large base. Amazon's cash flow compression is the one balance sheet I would not pay up for right now.",
        "views": [
            {"ticker": "MSFT", "stance": "long", "confidence": 0.8, "note": "Azure +35%, 40%+ operating margin.", "sources": ["sec-msft-10q-q1fy23"]},
            {"ticker": "AAPL", "stance": "long", "confidence": 0.7, "note": "Services mix lifting gross margin.", "sources": ["sec-aapl-10k-2022"]},
            {"ticker": "UNH", "stance": "long", "confidence": 0.7, "note": "Defensive growth, outlook reaffirmed.", "sources": ["sec-unh-10q-q3-2022"]},
            {"ticker": "NVDA", "stance": "long", "confidence": 0.6, "note": "Data center is the business now.", "sources": ["sec-nvda-10q-q3fy23"]},
            {"ticker": "XOM", "stance": "neutral", "confidence": 0.6, "note": "Peak earnings; balance sheet pristine.", "sources": ["sec-xom-10q-q3-2022"]},
            {"ticker": "AMZN", "stance": "avoid", "confidence": 0.6, "note": "OCF down 27% TTM, capex still rising.", "sources": ["sec-amzn-10q-q3-2022"]},
        ],
    },
    {
        "analyst": "macro", "date": "2022-12-30",
        "headline": "Inflation rolling over, curve says recession, Fed says higher for longer",
        "body": "Five months of decelerating CPI against a Fed still guiding to 5.1%. The 2s10s inversion is the deepest in four decades. Historically this favours quality balance sheets and long-duration growth once the last hike is in sight, and punishes cyclicals and rate-sensitive banks until the easing starts.",
        "views": [
            {"ticker": "JPM", "stance": "neutral", "confidence": 0.5, "note": "NII tailwind vs. reserve builds.", "sources": ["fred-t10y2y-2022-12", "sec-jpm-10q-q3-2022"]},
            {"ticker": "MSFT", "stance": "long", "confidence": 0.6, "note": "Duration beneficiary as hikes end.", "sources": ["fred-cpi-2022-11", "fred-fedfunds-2022-12"]},
            {"ticker": "PG", "stance": "long", "confidence": 0.6, "note": "Staples hold up into a slowdown.", "sources": ["fred-unrate-2022-12"]},
            {"ticker": "CAT", "stance": "neutral", "confidence": 0.5, "note": "Inversion argues caution on cyclicals.", "sources": ["fred-t10y2y-2022-12"]},
        ],
    },
    {
        "analyst": "sentiment", "date": "2022-12-30",
        "headline": "Tone bottoming on China, still negative on chips and energy",
        "body": "Media tone on China turned positive in the last two weeks of December as reopening became explicit. Semiconductor export-control coverage stayed negative all quarter. Energy coverage is high volume and negative in tone, which has been bullish for XOM's stock all year.",
        "views": [
            {"ticker": "AAPL", "stance": "neutral", "confidence": 0.5, "note": "Foxconn tone very negative, but reopening helps.", "sources": ["gdelt-apple-foxconn", "gdelt-china-reopen"]},
            {"ticker": "NVDA", "stance": "neutral", "confidence": 0.5, "note": "Export controls dominate coverage.", "sources": ["gdelt-chips-export"]},
            {"ticker": "CAT", "stance": "long", "confidence": 0.6, "note": "China reopening narrative.", "sources": ["gdelt-china-reopen"]},
        ],
    },
    {
        "analyst": "geopolitics", "date": "2022-12-30",
        "headline": "Energy security stays bid; chip controls are structural",
        "body": "The EU price cap on Russian crude and continued pipeline risk keep a floor under energy. The October export rule on advanced chips is not a one-quarter event, but it caps a Chinese share NVIDIA was already losing. China's reopening is the largest positive swing factor for the first half of 2023.",
        "views": [
            {"ticker": "XOM", "stance": "long", "confidence": 0.7, "note": "Sanctions regime supports pricing.", "sources": ["gdelt-ukraine-energy"]},
            {"ticker": "NVDA", "stance": "neutral", "confidence": 0.5, "note": "Controls cap China revenue, ~25% of DC.", "sources": ["gdelt-chips-export"]},
            {"ticker": "CAT", "stance": "long", "confidence": 0.6, "note": "Reopening plus infrastructure spend.", "sources": ["gdelt-china-reopen"]},
            {"ticker": "AAPL", "stance": "neutral", "confidence": 0.5, "note": "Supply chain concentration risk is visible now.", "sources": ["gdelt-apple-foxconn"]},
        ],
    },
]

WEIGHTS = [
    {"ticker": "MSFT", "weight": 0.16, "rationale": "Strongest fundamental and macro agreement in the book. Cloud growth plus duration tailwind once hikes stop.",
     "changes_my_mind": "Cut to 8% if Azure growth prints below 25% or FEDFUNDS guidance moves above 5.5%.",
     "analyst_influence": {"fundamentals": 0.5, "macro": 0.3, "technical": 0.1, "sentiment": 0.05, "geopolitics": 0.05}},
    {"ticker": "XOM", "weight": 0.14, "rationale": "Trend, geopolitics and balance sheet all agree. Fundamentals flag peak earnings, so this is sized as a trend position, not a value one.",
     "changes_my_mind": "Exit if price closes below the 200dma or Brent trades under $70 for a month.",
     "analyst_influence": {"technical": 0.4, "geopolitics": 0.35, "fundamentals": 0.2, "sentiment": 0.05}},
    {"ticker": "AAPL", "weight": 0.12, "rationale": "Fundamentals long, everyone else neutral. Oversold with a margin story; supply-chain risk keeps it from a top weight.",
     "changes_my_mind": "Add to 16% on a reclaim of the 200dma. Cut if Services growth drops below 10%.",
     "analyst_influence": {"fundamentals": 0.5, "technical": 0.2, "sentiment": 0.15, "geopolitics": 0.15}},
    {"ticker": "UNH", "weight": 0.12, "rationale": "Defensive growth with a reaffirmed outlook. Carries the book if the curve is right about a recession.",
     "changes_my_mind": "Cut if medical care ratio exceeds 83% for two quarters.",
     "analyst_influence": {"fundamentals": 0.6, "macro": 0.4}},
    {"ticker": "CAT", "weight": 0.11, "rationale": "Breakout plus China reopening. Macro is cautious on cyclicals, so sized below the trend evidence alone would suggest.",
     "changes_my_mind": "Cut to 5% if the reopening stalls (GDELT China tone back below -2) or price loses $220.",
     "analyst_influence": {"technical": 0.35, "sentiment": 0.25, "geopolitics": 0.25, "macro": 0.15}},
    {"ticker": "NVDA", "weight": 0.10, "rationale": "Fundamentals see the data-center pivot; technicals and geopolitics are not convinced yet. Half-size until price confirms.",
     "changes_my_mind": "Double on a close above $170. Cut if data-center growth turns negative y/y.",
     "analyst_influence": {"fundamentals": 0.45, "technical": 0.25, "geopolitics": 0.2, "sentiment": 0.1}},
    {"ticker": "PG", "weight": 0.09, "rationale": "Pure macro hedge. Staples should hold if the inversion is right.",
     "changes_my_mind": "Rotate out to cyclicals once the curve re-steepens.",
     "analyst_influence": {"macro": 0.8, "fundamentals": 0.2}},
    {"ticker": "GOOGL", "weight": 0.07, "rationale": "No analyst has a strong view. Held near equal weight on valuation alone.",
     "changes_my_mind": "Any analyst moving to a stance with confidence above 0.6.",
     "analyst_influence": {"fundamentals": 0.5, "macro": 0.5}},
    {"ticker": "JPM", "weight": 0.06, "rationale": "Macro split: NII tailwind against reserve builds and an inverted curve. Underweight.",
     "changes_my_mind": "Add once the 2s10s turns positive or reserve builds stop.",
     "analyst_influence": {"macro": 0.7, "fundamentals": 0.3}},
    {"ticker": "AMZN", "weight": 0.03, "rationale": "Both fundamentals and technicals say avoid. Token weight only so the position stays on the screen.",
     "changes_my_mind": "Add on a return to positive free cash flow growth.",
     "analyst_influence": {"fundamentals": 0.5, "technical": 0.5}},
]

assert abs(sum(w["weight"] for w in WEIGHTS) - 1.0) < 1e-9, "weights must sum to 1"


def business_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def walk(n: int, drift_annual: float, vol_annual: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    mu, sigma = drift_annual / 252, vol_annual / math.sqrt(252)
    level, out = 1.0, []
    for _ in range(n):
        level *= math.exp(mu - 0.5 * sigma**2 + sigma * rng.gauss(0, 1))
        out.append(round(level, 4))
    return out


def metrics(curve: list[float], rf: float = 0.0433) -> dict:
    n = len(curve)
    total = curve[-1] / curve[0] - 1
    years = n / 252
    cagr = (curve[-1] / curve[0]) ** (1 / years) - 1
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, n)]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    sharpe = (mean * 252 - rf) / (math.sqrt(var) * math.sqrt(252))
    return {"total_return": round(total, 4), "cagr": round(cagr, 4),
            "max_drawdown": round(mdd, 4), "sharpe": round(sharpe, 2)}


def main() -> None:
    days = business_days(date.fromisoformat(CUTOFF), END)
    n = len(days)
    portfolio = walk(n, 0.22, 0.17, seed=7)
    equal_weight = walk(n, 0.17, 0.18, seed=11)
    spy = walk(n, 0.19, 0.15, seed=3)

    resp = {
        "universe": UNIVERSE,
        "cutoff": CUTOFF,
        "baseline": "equal_weight",
        "sources": SOURCES,
        "memos": MEMOS,
        "weights": WEIGHTS,
        "equity": {
            "dates": [d.isoformat() for d in days],
            "portfolio": portfolio,
            "equal_weight": equal_weight,
            "spy": spy,
        },
        "metrics": {"portfolio": metrics(portfolio), "baseline": metrics(equal_weight)},
    }
    out = Path(__file__).with_name(f"run_{CUTOFF}.json")
    out.write_text(json.dumps(resp, indent=1), encoding="utf-8")
    print(f"wrote {out} ({n} days)")


if __name__ == "__main__":
    main()

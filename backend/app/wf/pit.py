"""Strict point-in-time (PIT) data layer for the walk-forward backtest (hub D15).

Visibility rules for a decision made after the close on ``as_of``:
    prices   rows with date <= as_of
    SEC      filings (fundamentals and 8-Ks) with filed < as_of, strictly before
    FRED     rows with available <= as_of
No fixture or mock fallback: no evidence means ``(digest, [])`` and the caller abstains.
This module must not import backend.app.wf.market (engine-only) or the legacy loaders.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.schema import Analyst, Source

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "wf"
MAX_DIGEST_CHARS = 5800
SENTIMENT_WEEKS = 8
REFERENCE = "SPY"
HORIZONS = {"1w": 5, "4w": 20, "12w": 60, "26w": 130}
ATR_N = 14
CORE_MACRO = ["FEDFUNDS", "CPIAUCSL", "UNRATE", "DGS10", "T10Y2Y"]
PCT_CHANGE_SERIES = {"CPIAUCSL", "USEPUINDXD", "DCOILWTICO", "VIXCLS"}
GEO_SERIES = ["VIXCLS", "USEPUINDXD", "BAMLH0A0HYM2", "T10Y2Y", "DCOILWTICO"]
GEO_ITEMS = {"1.05", "7.01", "8.01"}
SERIES_LABEL = {
    "FEDFUNDS": "Effective fed funds rate (%)",
    "CPIAUCSL": "CPI index (all urban consumers)",
    "UNRATE": "Unemployment rate (%)",
    "DGS10": "10y Treasury yield (%)",
    "T10Y2Y": "10y-2y Treasury spread (pp)",
    "VIXCLS": "VIX close",
    "BAMLH0A0HYM2": "ICE BofA US high-yield OAS (%)",
    "USEPUINDXD": "Economic policy uncertainty index (daily)",
    "DCOILWTICO": "WTI crude oil ($/bbl)",
}


def _fmt(x: float | None, nd: int = 1, suffix: str = "") -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}{suffix}"


def _pct(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.{nd}f}%"


def _money(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"${x / 1e9:,.2f}B"


def _atr(df: pd.DataFrame, n: int = ATR_N) -> float | None:
    if len(df) < n + 1:
        return None
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.iloc[-n:].mean())


def _rsi(close: pd.Series, n: int = 14) -> float | None:
    if len(close) < n + 1:
        return None
    d = close.diff().dropna()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return 100.0 if loss == 0 else float(100 - 100 / (1 + gain / loss))


def _ret(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1)


class PitData:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.audit: list[tuple[str, str, str | None]] = []
        self._prices = self._load_prices()
        self._macro = self._load_csv("fred/macro.csv", ["date", "available"])
        self._fund = self._load_csv("sec/fundamentals.csv", ["period_end", "filed"])
        self._k8 = self._load_8k()

    # ------------------------------------------------------------------ loading

    def _load_csv(self, rel: str, dates: list[str]) -> pd.DataFrame:
        path = self.data_dir / rel
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        for c in dates:
            df[c] = df[c].astype(str)
        return df

    def _load_prices(self) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for p in sorted((self.data_dir / "prices").glob("*.csv")):
            df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
            out[p.stem] = df[["open", "high", "low", "close", "volume"]].astype(float)
        return out

    def _load_8k(self) -> pd.DataFrame:
        df = self._load_csv("sec/filings_8k.csv", ["filed", "accepted"])
        if df.empty:
            return df
        for c in ("items", "item_titles", "description", "url"):
            df[c] = df[c].fillna("").astype(str)
        acc = pd.to_datetime(df["accepted"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
        df["accepted_et"] = acc
        df["accepted_et_date"] = acc.dt.strftime("%Y-%m-%d").fillna(df["filed"])
        return df

    # --------------------------------------------------------------- visibility

    def _bars(self, ticker: str, as_of: str) -> pd.DataFrame | None:
        df = self._prices.get(ticker)
        if df is None:
            return None
        sub = df.loc[: pd.Timestamp(as_of)]
        return sub if len(sub) else None

    def _visible_8k(self, as_of: str) -> pd.DataFrame:
        if self._k8.empty:
            return self._k8
        k = self._k8
        return k[(k["filed"] < as_of) & (k["accepted_et_date"] < as_of)]

    def _visible_fund(self, as_of: str) -> pd.DataFrame:
        f = self._fund
        return f if f.empty else f[f["filed"] < as_of]

    def _visible_macro(self, as_of: str) -> pd.DataFrame:
        m = self._macro
        return m if m.empty else m[m["available"] <= as_of]

    # --------------------------------------------------------------- public API

    def last_close(self, as_of: str, ticker: str) -> float:
        bars = self._bars(ticker, as_of)
        if bars is None:
            raise KeyError(f"no price for {ticker} on or before {as_of}")
        return float(bars["close"].iloc[-1])

    def execution_context(self, as_of: str, tickers: Sequence[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for t in tickers:
            bars = self._bars(t, as_of)
            if bars is None:
                continue
            close = bars["close"]
            gaps = (bars["open"] / close.shift(1) - 1).abs().iloc[-60:].dropna()
            out[t] = {
                "last_close": float(close.iloc[-1]),
                "atr14": _atr(bars),
                "avg_volume20": float(bars["volume"].iloc[-20:].mean()),
                "avg_gap_pct": float(gaps.mean()) if len(gaps) else None,
                "ret_1w": _ret(close, HORIZONS["1w"]),
                "last_date": bars.index[-1].strftime("%Y-%m-%d"),
            }
        return out

    @property
    def max_evidence_date(self) -> str | None:
        """Latest underlying data date used by any evidence() call so far."""
        dates = [d for _, _, d in self.audit if d]
        return max(dates) if dates else None

    def evidence(self, analyst: Analyst, as_of: str, universe: Sequence[str]) -> tuple[str, list[Source]]:
        builder = {
            "technical": self._technical,
            "fundamentals": self._fundamentals,
            "macro": self._macro_evidence,
            "sentiment": self._sentiment,
            "geopolitics": self._geopolitics,
        }[analyst]
        lines, sources, max_dates = builder(as_of, list(universe))
        digest = self._digest(analyst, as_of, lines)
        max_date = max(max_dates) if max_dates else None
        bad = [s.id for s in sources if s.date > as_of]
        if bad or (max_date and max_date > as_of):  # defence in depth: never return future data
            raise AssertionError(f"PIT violation for {analyst} @ {as_of}: {bad} {max_date}")
        self.audit.append((analyst, as_of, max_date))
        return digest, sources

    @staticmethod
    def _digest(analyst: str, as_of: str, lines: list[str]) -> str:
        head = f"{analyst.upper()} evidence as of {as_of} (all data public by this date)."
        if not lines:
            return head + " No evidence available."
        text = head + "\n" + "\n".join(lines)
        return text if len(text) <= MAX_DIGEST_CHARS else text[:MAX_DIGEST_CHARS].rsplit("\n", 1)[0]

    # --------------------------------------------------------------- technical

    def _technical(self, as_of: str, universe: list[str]):
        lines, sources, dates = [], [], []
        spy = self._bars(REFERENCE, as_of)
        spy_close = spy["close"] if spy is not None else None
        for t in universe:
            bars = self._bars(t, as_of)
            if bars is None or len(bars) < 30:
                continue
            c = bars["close"]
            last = bars.index[-1].strftime("%Y-%m-%d")
            rets = {k: _ret(c, n) for k, n in HORIZONS.items()}
            sma50 = float(c.iloc[-50:].mean()) if len(c) >= 50 else None
            sma200 = float(c.iloc[-200:].mean()) if len(c) >= 200 else None
            hi = float(c.iloc[-252:].max())
            atr = _atr(bars)
            rs = {}
            for k in ("4w", "12w"):
                r_t = rets[k]
                r_s = _ret(spy_close, HORIZONS[k]) if spy_close is not None else None
                rs[k] = None if r_t is None or r_s is None else r_t - r_s
            text = (
                f"{t}: close {c.iloc[-1]:.2f} ({last}); ret 1w {_pct(rets['1w'])} 4w {_pct(rets['4w'])} "
                f"12w {_pct(rets['12w'])} 26w {_pct(rets['26w'])}; vs 50d mean "
                f"{_pct(None if sma50 is None else c.iloc[-1] / sma50 - 1)}, vs 200d mean "
                f"{_pct(None if sma200 is None else c.iloc[-1] / sma200 - 1)}; RSI14 {_fmt(_rsi(c))}; "
                f"drawdown from 52w high {_pct(c.iloc[-1] / hi - 1)}; ATR14 "
                f"{_fmt(None if atr is None else atr / c.iloc[-1] * 100, 2, '%')}; rel strength vs SPY "
                f"4w {_pct(rs['4w'])} 12w {_pct(rs['12w'])}"
            )
            lines.append(text)
            dates.append(last)
            sources.append(Source(id=f"px:{t}:{as_of}", kind="price", title=f"{t} daily prices through {last}",
                                  date=last, url=None, excerpt=text))
        return lines, sources, dates

    # ------------------------------------------------------------ fundamentals

    def _fundamentals(self, as_of: str, universe: list[str]):
        lines, sources, dates = [], [], []
        vis = self._visible_fund(as_of)
        if vis.empty:
            return lines, sources, dates
        for t in universe:
            q = vis[vis["ticker"] == t].sort_values(["period_end", "filed"])
            if q.empty:
                continue
            row = q.iloc[-1]
            rev, ni, debt = float(row["revenue"]), float(row["net_income"]), row["total_debt"]
            prior = self._year_ago(q, str(row["period_end"]))
            g_rev = g_ni = None
            if prior is not None:
                g_rev = rev / float(prior["revenue"]) - 1 if float(prior["revenue"]) else None
                g_ni = ni / float(prior["net_income"]) - 1 if float(prior["net_income"]) > 0 else None
            fy, fp = row["fy"], row["fp"]
            text = (
                f"{t} {int(fy)}{fp} (period end {row['period_end']}, filed {row['filed']} on {row['form']}): "
                f"revenue {_money(rev)}, net income {_money(ni)}, net margin {_pct(ni / rev if rev else None)}, "
                f"total debt {_money(float(debt) if pd.notna(debt) else None)}, "
                f"YoY revenue {_pct(g_rev)}, YoY net income {_pct(g_ni)}"
            )
            lines.append(text)
            dates += [str(row["filed"]), str(row["period_end"])]
            sources.append(Source(id=f"sec:{t}:{int(fy)}{fp}", kind="sec", title=f"{t} {int(fy)}{fp} {row['form']}",
                                  date=str(row["filed"]), url=None, excerpt=text))
        return lines, sources, dates

    @staticmethod
    def _year_ago(q: pd.DataFrame, period_end: str) -> pd.Series | None:
        target = pd.Timestamp(period_end) - pd.Timedelta(days=365)
        ends = pd.to_datetime(q["period_end"])
        near = q[(ends - target).abs() <= pd.Timedelta(days=21)]
        return None if near.empty else near.iloc[-1]

    # ------------------------------------------------------------------- macro

    def _series_rows(self, vis: pd.DataFrame, series: str) -> pd.DataFrame:
        s = vis[vis["series"] == series]
        return s.sort_values(["date", "available"])

    def _series_line(self, vis: pd.DataFrame, series: str, windows: tuple[int, ...]):
        s = self._series_rows(vis, series)
        if s.empty:
            return None
        last = s.iloc[-1]
        d_last = pd.Timestamp(last["date"])
        parts = [f"{SERIES_LABEL[series]}: {last['value']:.2f} (obs {last['date']}, public {last['available']})"]
        for m in windows:
            ref = s[pd.to_datetime(s["date"]) <= d_last - pd.DateOffset(months=m)]
            if ref.empty:
                parts.append(f"{m}m change n/a")
                continue
            old = float(ref.iloc[-1]["value"])
            if series in PCT_CHANGE_SERIES and old:
                parts.append(f"{m}m {_pct(float(last['value']) / old - 1)}")
            else:
                parts.append(f"{m}m {float(last['value']) - old:+.2f}")
        return str(last["date"]), str(last["available"]), "; ".join(parts), float(last["value"])

    def _macro_evidence(self, as_of: str, universe: list[str]):
        lines, sources, dates = [], [], []
        vis = self._visible_macro(as_of)
        if vis.empty:
            return lines, sources, dates
        for series in CORE_MACRO:
            res = self._series_line(vis, series, (3, 12))
            if res is None:
                continue
            obs, avail, text, _ = res
            lines.append(text)
            dates += [obs, avail]
            sources.append(Source(id=f"fred:{series}:{obs}", kind="fred", title=SERIES_LABEL[series],
                                  date=avail, url=f"https://fred.stlouisfed.org/series/{series}", excerpt=text))
        return lines, sources, dates

    # --------------------------------------------------------------- sentiment

    def _recent_8k(self, as_of: str, universe: list[str]) -> pd.DataFrame:
        k = self._visible_8k(as_of)
        if k.empty:
            return k
        start = (pd.Timestamp(as_of) - pd.Timedelta(weeks=SENTIMENT_WEEKS)).strftime("%Y-%m-%d")
        k = k[(k["filed"] >= start) & k["ticker"].isin(list(universe))]
        return k.sort_values(["ticker", "filed", "accession"])

    def _earnings_reaction(self, ticker: str, row: pd.Series, as_of: str) -> str | None:
        """Close-to-close move around an earnings release, only if both closes are <= as_of."""
        bars = self._bars(ticker, as_of)
        if bars is None:
            return None
        acc = row["accepted_et"]
        after_close = pd.notna(acc) and acc.hour >= 16
        filed = pd.Timestamp(row["filed"])
        idx = bars.index
        if after_close:
            before = idx[idx <= filed]
            after = idx[idx > filed]
        else:
            before = idx[idx < filed]
            after = idx[idx >= filed]
        if len(before) == 0 or len(after) == 0:
            return None
        c0, c1 = float(bars.loc[before[-1], "close"]), float(bars.loc[after[0], "close"])
        return f"price reaction {before[-1]:%Y-%m-%d} to {after[0]:%Y-%m-%d} close {_pct(c1 / c0 - 1)}"

    def _sentiment(self, as_of: str, universe: list[str]):
        lines, sources, dates = [], [], []
        for _, r in self._recent_8k(as_of, universe).iterrows():
            react = self._earnings_reaction(r["ticker"], r, as_of) if "2.02" in r["items"].split(",") else None
            text = f"{r['ticker']} {r['form']} filed {r['filed']}: {r['item_titles'] or 'no items'}"
            if r["description"]:
                text += f" ({r['description']})"
            if react:
                text += f"; {react}"
            lines.append(text)
            dates.append(r["filed"])
            sources.append(Source(id=f"sec8k:{r['ticker']}:{r['accession']}", kind="sec",
                                  title=f"{r['ticker']} {r['form']} {r['filed']}", date=r["filed"],
                                  url=r["url"] or None, excerpt=text))
        return lines, sources, dates

    # ------------------------------------------------------------- geopolitics

    def _geopolitics(self, as_of: str, universe: list[str]):
        lines, sources, dates = [], [], []
        vis = self._visible_macro(as_of)
        for series in GEO_SERIES if not vis.empty else []:
            res = self._series_line(vis, series, (1, 3))
            if res is None:
                continue
            obs, avail, text, _ = res
            lines.append(text)
            dates += [obs, avail]
            sources.append(Source(id=f"fred:{series}:{obs}", kind="fred", title=SERIES_LABEL[series],
                                  date=avail, url=f"https://fred.stlouisfed.org/series/{series}", excerpt=text))
        recent = self._recent_8k(as_of, universe)
        for _, r in recent.iterrows():
            items = set(r["items"].split(","))
            if not items & GEO_ITEMS:
                continue
            hit = "; ".join(f"{i} {self._title(i)}" for i in sorted(items & GEO_ITEMS))
            text = f"{r['ticker']} {r['form']} filed {r['filed']}: {hit}"
            lines.append(text)
            dates.append(r["filed"])
            sources.append(Source(id=f"sec8k:{r['ticker']}:{r['accession']}", kind="sec",
                                  title=f"{r['ticker']} {r['form']} {r['filed']}", date=r["filed"],
                                  url=r["url"] or None, excerpt=text))
        return lines, sources, dates

    @staticmethod
    def _title(item: str) -> str:
        return {"1.05": "Material Cybersecurity Incidents", "7.01": "Regulation FD Disclosure",
                "8.01": "Other Events"}[item]


@functools.lru_cache(maxsize=1)
def default_pit() -> PitData:
    return PitData()

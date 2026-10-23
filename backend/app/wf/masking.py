"""Ticker/company masker for the memorization audit (hub D15 rule 4).

Protocol (exactly what analysts.py / pipeline.py call):
    masker.encode(text) -> str        used on a bare ticker ("AAPL" -> "S03") AND on free text
    masker.decode_ticker(code) -> str "S03" -> "AAPL" (KeyError on an unknown code)
Stages run in code space; pipeline un-masks plans and orders afterwards.

What is scrubbed: tickers (whole word, case-sensitive), company names and an alias table
(products, brands, executives; case-insensitive, longest first, word boundaries), SEC CIKs in
10-digit form (also inside accession numbers) and "CIK 320193" style unpadded numbers.
A few ambiguous aliases (Chase, Windows, Azure, ...) match only with their written
capitalisation to avoid eating ordinary words.

KNOWN LIMITS. Masking reduces, but cannot eliminate, recall: the model can still infer the
company from financial magnitudes (revenue, share price level, segment names), from
unlisted product names, or from events it remembers. The sector tag is NOT added: the
protocol has no place for it (strategy/execution prompts are built inside pipeline.py), so
`sector()` is exposed for reporting only. Codes are a seeded shuffle of the sorted
universe so code order does not leak alphabetical order.
"""

from __future__ import annotations

import random
import re

from data.common import CIKS, COMPANY_NAMES

SECTORS: dict[str, str] = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "GOOGL": "Communication Services",
    "JPM": "Financials",
    "XOM": "Energy",
    "UNH": "Health Care",
    "PG": "Consumer Staples",
    "CAT": "Industrials",
}

# Case-insensitive aliases (names, products, brands, executives).
ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("Apple", "iPhone", "iPad", "iOS", "iPadOS", "macOS", "MacBook", "AirPods",
             "Apple Watch", "App Store", "Vision Pro", "Apple Intelligence", "Siri",
             "Tim Cook", "Cupertino"),
    "MSFT": ("Microsoft", "Office 365", "Microsoft 365", "Copilot", "Xbox", "LinkedIn",
             "GitHub", "Satya Nadella", "Redmond", "Bing"),
    "NVDA": ("Nvidia", "CUDA", "GeForce", "Blackwell", "Hopper", "H100", "H200", "B200",
             "DGX", "Mellanox", "Jensen Huang"),
    "AMZN": ("Amazon", "Amazon.com", "AWS", "Amazon Web Services", "Prime Video",
             "Prime Day", "Alexa", "Kindle", "Whole Foods", "Twitch", "Zoox", "Andy Jassy"),
    "GOOGL": ("Alphabet", "Google", "Google Cloud", "YouTube", "Gemini Pro", "Waymo",
              "DeepMind", "Fitbit", "Sundar Pichai", "Mountain View"),
    "JPM": ("JPMorgan", "JPMorganChase", "JPMorgan Chase", "J.P. Morgan", "JP Morgan",
            "Jamie Dimon", "First Republic"),
    "XOM": ("Exxon", "ExxonMobil", "Exxon Mobil", "Esso", "XTO", "Darren Woods"),
    "UNH": ("UnitedHealth", "UnitedHealthcare", "United Healthcare", "UnitedHealth Group",
            "Optum", "OptumRx", "OptumHealth", "Change Healthcare", "Andrew Witty",
            "Stephen Hemsley"),
    "PG": ("Procter & Gamble", "Procter and Gamble", "Pampers", "Gillette", "Oral-B",
           "Olay", "Head & Shoulders", "Charmin", "Febreze", "Downy", "Pantene",
           "Swiffer", "Jon Moeller"),
    "CAT": ("Caterpillar", "Cat Inc", "Cat Financial", "Jim Umpleby", "Joe Creed"),
}

# Ambiguous with ordinary words: matched only with exactly this capitalisation.
STRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "MSFT": ("Windows", "Azure"),
    "GOOGL": ("Android", "Chrome", "Pixel", "Gemini"),
    "JPM": ("Chase",),
    "XOM": ("Mobil",),
    "PG": ("Tide", "Crest", "Bounty"),
}

_L = r"(?<![A-Za-z0-9])"
_R = r"(?![A-Za-z0-9])"


def _alternation(words: list[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(set(words), key=lambda w: (-len(w), w)))


class Masker:
    def __init__(self, universe: list[str] | tuple[str, ...] | None = None, seed: int = 0):
        known = sorted(set(universe or ()) | set(COMPANY_NAMES))
        order = list(known)
        random.Random(seed).shuffle(order)
        self._code = {t: f"S{i + 1:02d}" for i, t in enumerate(order)}
        self._ticker = {c: t for t, c in self._code.items()}
        self._alias_map = self._build_alias_map(known, ALIASES, lower=True)
        self._strict_map = self._build_alias_map(known, STRICT_ALIASES, lower=False)
        self._alias_re = self._compile(list(self._alias_map), re.IGNORECASE)
        self._strict_re = self._compile(list(self._strict_map), 0)
        self._ticker_re = self._compile(known, 0)
        self._cik_by_num = {c: t for t, c in CIKS.items() if t in known}
        self._cik_pad_re = re.compile(r"(?<!\d)(" + "|".join(self._cik_by_num) + r")(?!\d)")
        self._cik_short_re = re.compile(
            r"(CIK[\s#:=]*)0*(" + "|".join(str(int(c)) for c in self._cik_by_num) + r")(?!\d)",
            re.IGNORECASE,
        )

    @staticmethod
    def _compile(words: list[str], flags: int) -> re.Pattern[str]:
        return re.compile(_L + "(" + _alternation(words) + ")" + _R, flags)

    def _build_alias_map(self, known, table, lower: bool) -> dict[str, str]:
        out: dict[str, str] = {}
        for t in known:
            words = list(table.get(t, ()))
            if lower:
                words.append(COMPANY_NAMES.get(t, ""))
            for w in words:
                if w:
                    out[w.lower() if lower else w] = t
        return out

    # ---------------------------------------------------------------- protocol

    def code_for(self, ticker: str) -> str:
        return self._code[ticker]

    def sector(self, ticker_or_code: str) -> str:
        return SECTORS.get(self._ticker.get(ticker_or_code, ticker_or_code), "Unknown")

    def decode_ticker(self, code: str) -> str:
        return self._ticker[code.strip().upper()]

    def encode(self, text: str) -> str:
        if text in self._code:
            return self._code[text]
        out = self._alias_re.sub(lambda m: self._code[self._alias_map[m.group(0).lower()]], text)
        out = self._strict_re.sub(lambda m: self._code[self._strict_map[m.group(0)]], out)
        out = self._ticker_re.sub(lambda m: self._code[m.group(0)], out)
        out = self._cik_pad_re.sub(lambda m: self._code[self._cik_by_num[m.group(0)]], out)
        return self._cik_short_re.sub(self._short_cik, out)

    def _short_cik(self, m: re.Match[str]) -> str:
        padded = m.group(2).zfill(10)
        return m.group(1) + self._code[self._cik_by_num[padded]]

    def decode_text(self, text: str) -> str:
        """Best effort reverse for display: replaces codes by tickers."""
        return re.sub(r"\bS\d{2}\b", lambda m: self._ticker.get(m.group(0), m.group(0)), text)

    def leaks(self, text: str) -> list[str]:
        """Names, tickers or CIKs still present in already-encoded text (for audits/tests)."""
        found = [m.group(0) for r in (self._alias_re, self._strict_re, self._ticker_re,
                                       self._cik_pad_re) for m in r.finditer(text)]
        return found + [m.group(0) for m in self._cik_short_re.finditer(text)]


class MaskedPit:
    """Wraps a PitData so source ids, urls, titles and excerpts are masked too.

    analysts.build_prompt masks title/excerpt/digest with `masker.encode` but prints `s.id`
    raw, and PIT ids embed the ticker ("px:AAPL:2025-11-07"), which would hand the model the
    answer. Rewriting ids here keeps the id check inside run_analyst_strict consistent (it
    validates cited ids against the sources this wrapper returned). Everything else
    (execution_context, last_close, ...) is delegated unchanged; the pipeline maps its keys.
    """

    def __init__(self, pit, masker: Masker) -> None:
        self._pit, self._masker = pit, masker

    def __getattr__(self, name: str):
        return getattr(self._pit, name)

    def evidence(self, analyst: str, as_of: str, universe: list[str]):
        digest, sources = self._pit.evidence(analyst, as_of, universe)
        enc = self._masker.encode
        masked = [
            s.model_copy(update={
                "id": enc(s.id), "title": enc(s.title), "excerpt": enc(s.excerpt),
                "url": enc(s.url) if s.url else s.url,
            })
            for s in sources
        ]
        return enc(digest), masked

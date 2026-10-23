"""Shared constants for the fetch scripts and api/data.py."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent

UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "UNH", "PG", "CAT"]
REFERENCE = "SPY"
ALL_TICKERS = UNIVERSE + [REFERENCE]

# Company names as they appear in news text, used for GDELT tone queries.
COMPANY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMZN": "Amazon",
    "GOOGL": "Google",
    "JPM": "JPMorgan",
    "XOM": "ExxonMobil",
    "UNH": "UnitedHealth",
    "PG": "Procter & Gamble",
    "CAT": "Caterpillar",
}

# SEC CIKs (10 digits, zero padded) for the companyfacts API.
CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "JPM": "0000019617",
    "XOM": "0000034088",
    "UNH": "0000731766",
    "PG": "0000080424",
    "CAT": "0000018230",
}

FRED_SERIES = ["CPIAUCSL", "FEDFUNDS", "DGS10", "UNRATE"]

START = "2021-01-01"
END = "2025-06-30"

USER_AGENT = "TheDesk hackathon research desk (talasila.chaithu1@gmail.com)"

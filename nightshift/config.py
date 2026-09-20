"""Venue constants and universe. Numbers are Bitget-documented or labeled policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Bitget weekend rToken limit-order band vs pre-switch close (support FAQ).
RTOKEN_WEEKEND_LIMIT_BAND = 0.20

# Stock-perp index may not run more than ~10% from last external close while cash is dark.
STOCK_PERP_INDEX_MAX_DEV = 0.10

# Official mark is clamp(calc, index*(1-d), index*(1+d)). Default d=3%;
# English TradFi pair table lists 5% for NVDA/AAPL/TSLA/QQQ.
STOCK_PERP_MARK_CLAMP = 0.03
STOCK_PERP_MARK_CLAMP_BY_SYMBOL = {
    "NVDAUSDT": 0.05,
    "AAPLUSDT": 0.05,
    "TSLAUSDT": 0.05,
    "QQQUSDT": 0.05,
}


def mark_clamp_for(symbol: str) -> float:
    return STOCK_PERP_MARK_CLAMP_BY_SYMBOL.get(symbol.upper(), STOCK_PERP_MARK_CLAMP)

# Display MMR used to mimic a loose Bitget-style "margin ratio" (equity / MM).
# Real Bitget ladders vary by tier; this is labeled display-only.
DISPLAY_MMR = 0.01

# Nightshift policy: margin resource must cover IM plus this buffer after p90.
POLICY_IM_BUFFER = 0.15

# Spot / futures taker fees used when the kernel converts or cuts (Bitget promo/standard).
SPOT_TAKER_FEE = 0.0005
FUTURES_TAKER_FEE = 0.0006

# Default rToken collateral ratio (Bitget documents up to 95%; 90% is a typical mid tier).
DEFAULT_COLLATERAL_RATIO = 0.90

BITGET_PUBLIC = "https://api.bitget.com"


@dataclass(frozen=True)
class Name:
    ticker: str
    rtoken_spot: str | None
    stock_perp: str | None
    crypto_perp: str | None
    weekend_spot: bool
    is_equity: bool


UNIVERSE: dict[str, Name] = {
    "NVDA": Name("NVDA", "RNVDAUSDT", "NVDAUSDT", None, True, True),
    "AAPL": Name("AAPL", "RAAPLUSDT", "AAPLUSDT", None, True, True),
    "TSLA": Name("TSLA", "RTSLAUSDT", "TSLAUSDT", None, True, True),
    "QQQ": Name("QQQ", "RQQQUSDT", "QQQUSDT", None, True, True),
    "BTC": Name("BTC", None, None, "BTCUSDT", False, False),
    "ETH": Name("ETH", None, None, "ETHUSDT", False, False),
}

# Historical-style gap buckets. Labeled as policy, not a forecast.
# Idiosyncratic mega-cap news / earnings-like (S&P names often gap ≥3% on earnings days).
IDIO_GAPS = {"p50": -0.04, "p90": -0.10, "p99": -0.18}
EARNINGS_GAPS = {"p50": -0.05, "p90": -0.12, "p99": -0.22}
MACRO_GAPS = {"p50": -0.015, "p90": -0.04, "p99": -0.08}
QUIET_GAPS = {"p50": -0.004, "p90": -0.015, "p99": -0.03}
ZERO_GAPS = {"p50": 0.0, "p90": 0.0, "p99": 0.0}

NEWS_TO_TICKERS = {
    "none": [],
    "crypto_beta": [],
    "nvidia_idio": ["NVDA"],
    "apple_idio": ["AAPL"],
    "tesla_idio": ["TSLA"],
    "mega_tech": ["NVDA", "AAPL", "QQQ"],
    "macro": ["NVDA", "AAPL", "TSLA", "QQQ"],
    "earnings": ["NVDA"],
}

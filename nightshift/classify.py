"""News classifier. LLM is optional; keyword rules always run so the kernel never waits on a model."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from nightshift.config import (
    EARNINGS_GAPS,
    IDIO_GAPS,
    MACRO_GAPS,
    NEWS_TO_TICKERS,
    QUIET_GAPS,
    ZERO_GAPS,
)

VALID_LABELS = (
    "none",
    "crypto_beta",
    "nvidia_idio",
    "apple_idio",
    "tesla_idio",
    "mega_tech",
    "macro",
    "earnings",
)


@dataclass
class News:
    label: str
    tickers: list[str]
    confidence: float
    rationale: str
    headline: str
    llm_used: bool = False
    gaps: dict[str, dict[str, float]] | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def gap_book(news: News) -> dict[str, dict[str, float]]:
    """Per-ticker p50/p90/p99 equity gaps. BTC is never gapped here — weekend BTC is already in the mark."""
    if news.gaps:
        return news.gaps
    table: dict[str, dict[str, float]] = {}
    if news.label == "none":
        for t in ("NVDA", "AAPL", "TSLA", "QQQ"):
            table[t] = dict(QUIET_GAPS)
        return table
    if news.label == "crypto_beta":
        for t in ("NVDA", "AAPL", "TSLA", "QQQ"):
            table[t] = dict(ZERO_GAPS)
        return table
    family = EARNINGS_GAPS if news.label == "earnings" else IDIO_GAPS
    if news.label == "macro":
        family = MACRO_GAPS
    hit = set(news.tickers) or set(NEWS_TO_TICKERS.get(news.label, []))
    for t in ("NVDA", "AAPL", "TSLA", "QQQ"):
        table[t] = dict(family) if t in hit else dict(QUIET_GAPS)
    return table


def classify_rules(headline: str) -> News:
    h = (headline or "").strip()
    if not h:
        return News("none", [], 0.95, "No headline. Quiet weekend gaps only.", "", False)
    low = h.lower()
    tickers = _tickers_in(low)
    if re.search(r"\bearnings\b|\beps\b|\bguidance\b|\b8-k\b|\bearnings call\b", low):
        return News("earnings", tickers or ["NVDA"], 0.8, "Earnings/guidance language. Use earnings gap buckets.", h, False)
    if re.search(r"\bfed\b|\bfomc\b|\brate cut\b|\brate hike\b|\bcpi\b|\bgeopolit", low):
        return News("macro", ["NVDA", "AAPL", "TSLA", "QQQ"], 0.75, "Macro/policy language.", h, False)
    crypto = bool(re.search(r"\bbitcoin\b|\bbtc\b|\bcrypto dump\b|\brisk[- ]off crypto", low))
    if crypto and not tickers:
        return News("crypto_beta", [], 0.85, "Crypto-only tape. Do not treat as NVIDIA cash news.", h, False)
    if "NVDA" in tickers or re.search(r"china chip|cuda|blackwell|h100|b200", low):
        return News("nvidia_idio", ["NVDA"], 0.86, "NVIDIA-specific event.", h, False)
    if "AAPL" in tickers or re.search(r"\biphone\b", low):
        return News("apple_idio", ["AAPL"], 0.86, "Apple-specific event.", h, False)
    if "TSLA" in tickers or re.search(r"\belon\b", low):
        return News("tesla_idio", ["TSLA"], 0.86, "Tesla-specific event.", h, False)
    if re.search(r"mega-?cap tech|magnificent 7|nasdaq panic", low):
        return News("mega_tech", ["NVDA", "AAPL", "QQQ"], 0.7, "Broad mega-cap tech shock.", h, False)
    return News("none", [], 0.55, "Headline did not match an idiosyncratic pattern. Quiet gaps.", h, False)


def _negated(low: str, word: str) -> bool:
    return bool(re.search(rf"\b(?:no|not|without|isn't|is not)\s+{re.escape(word)}\b", low))


def _tickers_in(low: str) -> list[str]:
    found = []
    for word, ticker in (
        ("nvidia", "NVDA"),
        ("nvda", "NVDA"),
        ("apple", "AAPL"),
        ("aapl", "AAPL"),
        ("tesla", "TSLA"),
        ("tsla", "TSLA"),
        ("qqq", "QQQ"),
    ):
        if ticker not in found and not _negated(low, word):
            if re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", low):
                found.append(ticker)
    return found


def classify(headline: str, use_llm: bool = True) -> News:
    base = classify_rules(headline)
    if not use_llm or not (headline or "").strip():
        return base
    polished = _try_llm(headline, base)
    if not polished:
        return base
    # Gap-critical rules win. LLM may not invent an equity gap on a crypto-only tape.
    if base.label in {"crypto_beta", "none"} and polished.label != base.label:
        return base
    return polished


def _try_llm(headline: str, fallback: News) -> News | None:
    from nightshift.qwen import complete, configured

    if not configured():
        return None
    try:
        content = complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Classify a trading headline for a Bitget UTA weekend-risk agent. "
                        "Return JSON only: {\"label\": one of "
                        + json.dumps(list(VALID_LABELS))
                        + ", \"tickers\": [\"NVDA\"|\"AAPL\"|\"TSLA\"|\"QQQ\"], "
                        "\"confidence\": 0-1, \"rationale\": \"<=40 words\"}. "
                        "crypto_beta = bitcoin/crypto move with no equity-specific news. "
                        "You do not size trades. You do not invent numbers."
                    ),
                },
                {
                    "role": "user",
                    "content": "HEADLINE_START\n"
                    + headline[:500].replace("{", " ").replace("}", " ")
                    + "\nHEADLINE_END",
                },
            ],
            timeout=12.0,
        )
        data = _extract_json(content)
        label = data.get("label", fallback.label)
        if label not in VALID_LABELS:
            label = fallback.label
        tickers = [t for t in data.get("tickers", []) if t in {"NVDA", "AAPL", "TSLA", "QQQ"}]
        if not tickers:
            tickers = list(NEWS_TO_TICKERS.get(label, []))
        return News(
            label=label,
            tickers=tickers,
            confidence=float(data.get("confidence", 0.7)),
            rationale=str(data.get("rationale") or fallback.rationale)[:240],
            headline=headline,
            llm_used=True,
        )
    except Exception:
        return None


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)

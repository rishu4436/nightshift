"""Live paper book: seed and mark-to-market from Bitget public clocks."""

from __future__ import annotations

from nightshift.account import Account, Collateral, Perp, perp_to_equity_ticker
from nightshift.calendar import Session, session_at, weekend_session
from nightshift.classify import News, classify
from nightshift.clocks import fetch_clocks
from nightshift.config import DEFAULT_COLLATERAL_RATIO


def _nvda_row(clocks: dict) -> dict:
    for row in clocks.get("clocks") or []:
        if row.get("ticker") == "NVDA" and row.get("rtoken_last"):
            return row
    raise RuntimeError("NVDA rToken clock missing")


def live_book(
    clocks: dict | None = None,
    *,
    rnvda_usd: float = 10_000.0,
    btc_notional: float = 30_000.0,
    btc_leverage: float = 5.0,
    btc_already_move: float = -0.08,
    force_weekend: bool = True,
    headline: str = "",
) -> tuple[Account, Session, News, str, dict]:
    payload = clocks or fetch_clocks(weekend_session() if force_weekend else None)
    nvda = _nvda_row(payload)
    px = float(nvda["rtoken_last"])
    cash = float(nvda.get("cash_last") or px)
    btc = payload.get("btc") or {}
    if "mark" not in btc:
        raise RuntimeError(f"BTC clock missing: {btc}")
    btc_mark = float(btc["mark"])
    move = float(btc_already_move)
    entry = btc_mark / (1.0 + move) if move != 0.0 else btc_mark
    qty = btc_notional / btc_mark
    units = rnvda_usd / cash
    frozen = bool(payload.get("session", {}).get("collateral_index_frozen")) or force_weekend
    index = cash if frozen else px
    acct = Account(
        cash_usdt=0.0,
        collaterals=[
            Collateral("NVDA", units, index, px, cash, DEFAULT_COLLATERAL_RATIO),
        ],
        perps=[Perp("BTCUSDT", "long", qty, entry, btc_mark, btc_leverage, False)],
        label="live_book",
    )
    session = weekend_session() if force_weekend else session_at()
    news = classify(headline, use_llm=False) if headline.strip() else News(
        "nvidia_idio",
        ["NVDA"],
        0.8,
        "Live book default: treat as NVIDIA-idio so Monday p90 is the stress, not a quiet HOLD.",
        headline,
        False,
    )
    blurb = (
        f"Live Bitget marks. rNVDA last {px}, cash/index {cash}, BTC mark {btc_mark}. "
        f"Paper book: ${rnvda_usd:,.0f} rNVDA collateral, BTC {btc_leverage:.0f}x notional "
        f"${btc_notional:,.0f} with a {move:.0%} already-in-the-mark dump. "
        f"{'Weekend freeze forced so we can stress Monday-implied today.' if force_weekend else ''}"
    )
    return acct, session, news, blurb, payload


def apply_live_marks(account: Account, clocks: dict, *, freeze_index: bool) -> Account:
    nxt = account.clone()
    by_ticker = {c["ticker"]: c for c in clocks.get("clocks") or []}
    btc = clocks.get("btc") or {}
    for c in nxt.collaterals:
        row = by_ticker.get(c.ticker)
        if not row or not row.get("rtoken_last"):
            continue
        last = float(row["rtoken_last"])
        c.live_ref_usd = last
        if not freeze_index:
            c.index_usd = last
            if row.get("cash_last"):
                c.cash_close_usd = float(row["cash_last"])
    for p in nxt.perps:
        if p.symbol == "BTCUSDT" and btc.get("mark"):
            p.mark_usd = float(btc["mark"])
            continue
        if p.symbol == "ETHUSDT" and clocks.get("eth", {}).get("mark"):
            p.mark_usd = float(clocks["eth"]["mark"])
            continue
        ticker = perp_to_equity_ticker(p.symbol)
        row = by_ticker.get(ticker or "")
        if row and row.get("perp_mark"):
            mark = float(row["perp_mark"])
            idx = float(row["perp_index"] or mark)
            cash = None
            for c in nxt.collaterals:
                if c.ticker == ticker:
                    cash = c.cash_close_usd
                    break
            if freeze_index and cash:
                from nightshift.stress import clamp_index_to_external, clamp_mark_to_index

                idx = clamp_index_to_external(idx, cash)
                mark = clamp_mark_to_index(mark, idx, p.symbol)
            p.mark_usd = mark
    return nxt

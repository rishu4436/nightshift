"""Judge-facing scenarios. Prices are round so the autopsy is readable."""

from __future__ import annotations

from nightshift.account import Account, Collateral, Perp
from nightshift.calendar import Session, earnings_session, regular_session, weekend_session
from nightshift.classify import News
from nightshift.config import DEFAULT_COLLATERAL_RATIO


def _btc_long(notional_now: float, leverage: float, move: float, mark: float = 92_000.0) -> Perp:
    entry = mark / (1.0 + move)
    qty = notional_now / mark
    return Perp("BTCUSDT", "long", qty, entry, mark, leverage, is_stock=False)


def _nvda_collateral(index: float = 200.0, live: float | None = None, units_value: float = 10_000.0) -> Collateral:
    live = index if live is None else live
    units = units_value / index
    return Collateral("NVDA", units, index, live, cash_close_usd=index, ratio=DEFAULT_COLLATERAL_RATIO)


def frozen_illusion() -> tuple[Account, Session, News, str]:
    """rNVDA as UTA margin + BTC long. Index frozen. NVIDIA rumor. Screen looks funded."""
    acct = Account(
        cash_usdt=0.0,
        collaterals=[_nvda_collateral(200.0, live=198.0)],
        perps=[_btc_long(30_000, leverage=5, move=-0.08)],
        label="frozen_illusion",
    )
    news = News(
        label="nvidia_idio",
        tickers=["NVDA"],
        confidence=0.9,
        rationale="Weekend NVIDIA China-license rumor. Cash cannot print it.",
        headline="NVIDIA China chip license in doubt, Reuters — Saturday",
        llm_used=False,
    )
    blurb = (
        "You hold $10k rNVDA as UTA margin and a 5x BTC long that already lost 8%. "
        "Bitget froze the rNVDA index at Friday's close, so the screen still treats NVIDIA as $10k. "
        "Monday p90 (−10%) unfreezes that index and the account can no longer fund IM."
    )
    return acct, weekend_session(), news, blurb


def fake_hedge() -> tuple[Account, Session, News, str]:
    """Same book plus a short NVDA perp that can only print ±3% this weekend."""
    acct, session, news, _ = frozen_illusion()
    cash = 200.0
    mark = cash * 0.97  # clamped −3%
    qty = 10_000.0 / mark
    acct.perps.append(Perp("NVDAUSDT", "short", qty, cash, mark, leverage=5, is_stock=True))
    acct.label = "fake_hedge"
    blurb = (
        "Same frozen-collateral book, plus a short NVDAUSDT that looks like a hedge. "
        "The official mark is clamped to −3%. A −10% cash gap is unprintable until Monday. "
        "Nightshift refuses to treat that hedge as cover and still cuts live BTC."
    )
    return acct, session, news, blurb


def quiet_hold() -> tuple[Account, Session, News, str]:
    qqq = Collateral(
        "QQQ",
        units=10_000.0 / 400.0,
        index_usd=400.0,
        live_ref_usd=400.0,
        cash_close_usd=400.0,
        ratio=DEFAULT_COLLATERAL_RATIO,
    )
    acct = Account(0.0, [qqq], [], "quiet_hold")
    news = News("none", [], 0.95, "No headline.", "", False)
    blurb = "Tokenized QQQ, no leverage, no news. Kernel must HOLD. Doing nothing is a scored outcome."
    return acct, weekend_session(), news, blurb


def crypto_beta_only() -> tuple[Account, Session, News, str]:
    acct, session, _, _ = frozen_illusion()
    acct.label = "crypto_beta_only"
    news = News(
        "crypto_beta",
        [],
        0.88,
        "Bitcoin dumped. No NVIDIA-specific news.",
        "BTC −8% on Saturday, no NVDA headline",
        False,
    )
    blurb = (
        "Same UTA, but the headline is Bitcoin only. Nightshift must not invent an NVIDIA cash gap. "
        "Any cut is about live BTC IM, not a fake stock story."
    )
    return acct, session, news, blurb


def earnings_window() -> tuple[Account, Session, News, str]:
    nvda = _nvda_collateral(200.0, live=200.0)
    # Weekday after-hours: index is not weekend-frozen; cash tape is thin but not a Monday re-anchor.
    acct = Account(2_000.0, [nvda], [], "earnings_window")
    news = News(
        "earnings",
        ["NVDA"],
        0.84,
        "AMC print. Most of the jump historically lands 16:00–18:30 ET.",
        "NVIDIA reports after the close — 16:05 ET",
        False,
    )
    blurb = (
        "Weekday earnings window. rToken still routes toward cash books. "
        "Nightshift does not chase a weekend band. If the book already survives p90, it HOLDs."
    )
    return acct, earnings_session(), news, blurb


def cash_open_idle() -> tuple[Account, Session, News, str]:
    acct = Account(
        cash_usdt=1_000.0,
        collaterals=[_nvda_collateral(200.0, live=200.0)],
        perps=[_btc_long(10_000, leverage=5, move=0.0, mark=92_000.0)],
        label="cash_open_idle",
    )
    news = News("none", [], 0.9, "Regular hours, no headline.", "", False)
    blurb = "US cash is open. Frozen-index logic is off. Kernel HOLDs unless the live book is already broken."
    return acct, regular_session(), news, blurb


def double_long() -> tuple[Account, Session, News, str]:
    """rNVDA collateral plus a long NVDA perp — doubling down. Crypto cut cannot save it; convert must fire."""
    acct, session, news, _ = frozen_illusion()
    cash = 200.0
    mark = cash * 0.97
    qty = 40_000.0 / mark
    acct.perps.append(Perp("NVDAUSDT", "long", qty, cash, mark, leverage=5, is_stock=True))
    acct.label = "double_long"
    blurb = (
        "Long rNVDA as margin and long NVDAUSDT on top. Weekend mark is clamped. "
        "Cutting BTC is not enough; kernel must convert rNVDA to USDT."
    )
    return acct, session, news, blurb


def empty_book() -> tuple[Account, Session, News, str]:
    acct = Account(0.0, [], [], "empty_book")
    news = News("nvidia_idio", ["NVDA"], 0.9, "Headline with no position.", "NVIDIA rumor", False)
    return acct, weekend_session(), news, "Empty account. HOLD. Nothing to cut."


SCENARIOS = {
    "frozen_illusion": frozen_illusion,
    "fake_hedge": fake_hedge,
    "quiet_hold": quiet_hold,
    "crypto_beta_only": crypto_beta_only,
    "earnings_window": earnings_window,
    "cash_open_idle": cash_open_idle,
    "double_long": double_long,
    "empty_book": empty_book,
}


SCENARIO_META = {
    "frozen_illusion": ("Frozen index", "UI healthy · Monday dead"),
    "fake_hedge": ("Cosmetic hedge", "Clamped NVDA short"),
    "quiet_hold": ("Quiet HOLD", "No leverage, no news"),
    "crypto_beta_only": ("BTC beta", "No NVIDIA story"),
    "earnings_window": ("Earnings window", "16:00–18:30 ET"),
    "cash_open_idle": ("Cash open", "Freeze logic off"),
    "double_long": ("Double long", "Must convert / close"),
    "empty_book": ("Empty book", "Nothing to cut"),
}


def list_scenarios() -> list[dict]:
    rows = []
    for sid, fn in SCENARIOS.items():
        _, _, _, blurb = fn()
        title, kicker = SCENARIO_META.get(sid, (sid, ""))
        rows.append({"id": sid, "title": title, "kicker": kicker, "blurb": blurb})
    return rows


def load(scenario_id: str) -> tuple[Account, Session, News, str]:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"unknown scenario {scenario_id}")
    return SCENARIOS[scenario_id]()

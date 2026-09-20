from nightshift.account import Account, Collateral, Perp
from nightshift.calendar import session_at, weekend_session
from nightshift.config import DEFAULT_COLLATERAL_RATIO
from nightshift.stress import apply_monday_gaps, snapshot
from datetime import datetime
from zoneinfo import ZoneInfo


def test_weekend_session_freezes_collateral():
    s = weekend_session()
    assert s.collateral_index_frozen
    assert s.rtoken_weekend_book
    assert s.stock_perp_mark_clamped
    assert not s.cash_open


def test_saturday_calendar():
    ts = datetime(2026, 9, 12, 21, 0, tzinfo=ZoneInfo("America/New_York"))
    s = session_at(ts)
    assert s.kind == "weekend"
    assert s.collateral_index_frozen


def test_friday_night_freezes():
    ts = datetime(2026, 9, 11, 21, 0, tzinfo=ZoneInfo("America/New_York"))
    s = session_at(ts)
    assert s.collateral_index_frozen
    assert s.rtoken_weekend_book


def test_monday_preopen_still_frozen():
    ts = datetime(2026, 9, 14, 8, 0, tzinfo=ZoneInfo("America/New_York"))
    s = session_at(ts)
    assert s.collateral_index_frozen
    assert s.kind == "monday_preopen"


def test_monday_cash_open_unfreezes():
    ts = datetime(2026, 9, 14, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    s = session_at(ts)
    assert not s.collateral_index_frozen
    assert s.cash_open


def test_monday_unfreeze_drops_credit():
    c = Collateral("NVDA", 50, 200, 198, 200, DEFAULT_COLLATERAL_RATIO)
    p = Perp("BTCUSDT", "long", 0.3, 100_000, 92_000, 5, False)
    acct = Account(0, [c], [p])
    before = snapshot(acct)
    nxt = apply_monday_gaps(acct, {"NVDA": -0.10})
    after = snapshot(nxt)
    assert nxt.collaterals[0].index_usd == 180
    assert after.collateral_credit < before.collateral_credit
    assert after.equity < before.equity

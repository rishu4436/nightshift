"""US cash session vs Bitget weekend.

Collateral freeze follows Bitget's weekend book: Friday 20:00 ET after-hours
end through Monday 9:30 ET regular open (plus NYSE full-close holidays).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ET = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    ET = ZoneInfo("UTC")

NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
}

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARNINGS_WINDOW_END = time(18, 30)
AFTER_HOURS_END = time(20, 0)


@dataclass(frozen=True)
class Session:
    kind: str
    cash_open: bool
    cash_closed: bool
    collateral_index_frozen: bool
    rtoken_weekend_book: bool
    stock_perp_mark_clamped: bool
    earnings_window: bool
    label: str
    as_of_et: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "cash_open": self.cash_open,
            "cash_closed": self.cash_closed,
            "collateral_index_frozen": self.collateral_index_frozen,
            "rtoken_weekend_book": self.rtoken_weekend_book,
            "stock_perp_mark_clamped": self.stock_perp_mark_clamped,
            "earnings_window": self.earnings_window,
            "label": self.label,
            "as_of_et": self.as_of_et,
        }


def _is_holiday(d: date) -> bool:
    if d.year == 2026:
        return d in NYSE_HOLIDAYS_2026
    return False


def _weekend_book(weekday: int, t: time, holiday: bool) -> bool:
    if holiday:
        return True
    if weekday == 4 and t >= AFTER_HOURS_END:
        return True
    if weekday >= 5:
        return True
    if weekday == 0 and t < REGULAR_OPEN:
        return True
    return False


def session_at(now: datetime | None = None) -> Session:
    ts = now.astimezone(ET) if now else datetime.now(ET)
    d = ts.date()
    t = ts.timetz().replace(tzinfo=None)
    weekday = ts.weekday()
    holiday = _is_holiday(d)
    weekend_book = _weekend_book(weekday, t, holiday)
    frozen = weekend_book
    cash_open = (not weekend_book) and (not holiday) and REGULAR_OPEN <= t < REGULAR_CLOSE
    earnings = (not weekend_book) and (not holiday) and REGULAR_CLOSE <= t < EARNINGS_WINDOW_END
    after_hours = (not weekend_book) and (not holiday) and REGULAR_CLOSE <= t < AFTER_HOURS_END

    if weekday == 4 and t >= AFTER_HOURS_END:
        kind, label = "weekend", "WEEKEND BOOK — Fri 20:00 ET, rToken index frozen"
    elif weekday >= 5:
        kind, label = "weekend", "WEEKEND — cash dark, rToken index frozen"
    elif weekday == 0 and t < REGULAR_OPEN:
        kind, label = "monday_preopen", "MONDAY PRE-OPEN — frozen until 9:30 ET cash open"
    elif holiday:
        kind, label = "holiday", "US HOLIDAY — cash dark, rToken index frozen"
    elif cash_open:
        kind, label = "regular", "US CASH OPEN — rToken routes toward Nasdaq/NYSE"
    elif earnings:
        kind, label = "after_hours_earnings", "AFTER HOURS (earnings window 16:00–18:30 ET)"
    elif after_hours:
        kind, label = "after_hours", "AFTER HOURS — thin cash tape, index still live"
    elif t < REGULAR_OPEN:
        kind, label = "premarket", "PREMARKET — cash tape thin, index live"
    else:
        kind, label = "overnight", "OVERNIGHT — cash dark, perp mark clamped, index live"

    return Session(
        kind=kind,
        cash_open=cash_open,
        cash_closed=not cash_open,
        collateral_index_frozen=frozen,
        rtoken_weekend_book=weekend_book,
        stock_perp_mark_clamped=not cash_open,
        earnings_window=earnings,
        label=label,
        as_of_et=ts.strftime("%Y-%m-%d %H:%M ET"),
    )


def weekend_session(as_of: str = "2026-09-12 21:00 ET") -> Session:
    return Session(
        kind="weekend",
        cash_open=False,
        cash_closed=True,
        collateral_index_frozen=True,
        rtoken_weekend_book=True,
        stock_perp_mark_clamped=True,
        earnings_window=False,
        label="WEEKEND — cash dark, rToken index frozen",
        as_of_et=as_of,
    )


def earnings_session(as_of: str = "2026-09-16 16:10 ET") -> Session:
    return Session(
        kind="after_hours_earnings",
        cash_open=False,
        cash_closed=True,
        collateral_index_frozen=False,
        rtoken_weekend_book=False,
        stock_perp_mark_clamped=True,
        earnings_window=True,
        label="AFTER HOURS (earnings window 16:00–18:30 ET)",
        as_of_et=as_of,
    )


def regular_session(as_of: str = "2026-09-11 14:00 ET") -> Session:
    return Session(
        kind="regular",
        cash_open=True,
        cash_closed=False,
        collateral_index_frozen=False,
        rtoken_weekend_book=False,
        stock_perp_mark_clamped=False,
        earnings_window=False,
        label="US CASH OPEN — rToken routes toward Nasdaq/NYSE",
        as_of_et=as_of,
    )

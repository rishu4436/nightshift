"""Deterministic risk kernel. The LLM never calls this with a size. It only reads News."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from nightshift.account import Account, Perp, perp_to_equity_ticker
from nightshift.calendar import Session
from nightshift.classify import News, gap_book
from nightshift.config import (
    FUTURES_TAKER_FEE,
    POLICY_IM_BUFFER,
    RTOKEN_WEEKEND_LIMIT_BAND,
    SPOT_TAKER_FEE,
    mark_clamp_for,
)
from nightshift.stress import Snapshot, monday_snapshot, snapshot


@dataclass
class Leg:
    kind: str  # cut_live | convert_collateral
    symbol: str
    fraction: float
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Fill:
    ts: str
    instrument: str
    direction: str
    price: float
    quantity: float
    cash_delta: float
    kind: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price"] = round(self.price, 6)
        d["quantity"] = round(self.quantity, 8)
        d["cash_delta"] = round(self.cash_delta, 4)
        return d


@dataclass
class FakeHedge:
    symbol: str
    ticker: str
    implied_gap: float
    printable_now: float
    trapped: float
    side: str
    note: str

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("implied_gap", "printable_now", "trapped"):
            d[k] = round(d[k], 4)
        return d


@dataclass
class Decision:
    action: str
    reason: str
    legs: list[Leg] = field(default_factory=list)
    fake_hedges: list[FakeHedge] = field(default_factory=list)
    screen: Snapshot | None = None
    p50: Snapshot | None = None
    p90: Snapshot | None = None
    p99: Snapshot | None = None
    after: Snapshot | None = None
    news: News | None = None
    session: Session | None = None
    gap_book: dict | None = None
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "legs": [x.to_dict() for x in self.legs],
            "fake_hedges": [x.to_dict() for x in self.fake_hedges],
            "screen": self.screen.to_dict() if self.screen else None,
            "p50": self.p50.to_dict() if self.p50 else None,
            "p90": self.p90.to_dict() if self.p90 else None,
            "p99": self.p99.to_dict() if self.p99 else None,
            "after": self.after.to_dict() if self.after else None,
            "news": self.news.to_dict() if self.news else None,
            "session": self.session.to_dict() if self.session else None,
            "gap_book": self.gap_book,
            "explanation": self.explanation,
        }


def _percentile_gaps(book: dict[str, dict[str, float]], which: str) -> dict[str, float]:
    return {t: float(v[which]) for t, v in book.items()}


def detect_fake_hedges(account: Account, p90_gaps: dict[str, float]) -> list[FakeHedge]:
    out: list[FakeHedge] = []
    for p in account.perps:
        if not p.is_stock:
            continue
        ticker = perp_to_equity_ticker(p.symbol)
        if not ticker:
            continue
        gap = float(p90_gaps.get(ticker, 0.0))
        width = mark_clamp_for(p.symbol)
        if abs(gap) <= width + 1e-9:
            continue
        hedging = (gap < 0 and p.side == "short") or (gap > 0 and p.side == "long")
        if not hedging:
            continue
        printable = width if gap > 0 else -width
        trapped = gap - printable
        out.append(
            FakeHedge(
                symbol=p.symbol,
                ticker=ticker,
                implied_gap=gap,
                printable_now=printable,
                trapped=trapped,
                side=p.side,
                note=(
                    f"{p.symbol} {p.side} looks like a hedge for a {gap:.0%} cash gap, "
                    f"but the official mark is clamped to the index ±{width:.0%} until cash reopens. "
                    f"{abs(trapped):.0%} of the move is unprintable this weekend."
                ),
            )
        )
    return out


def _policy_fail(snap: Snapshot) -> bool:
    return (not snap.policy_ok) or (not snap.policy_buffer_ok)


def _crypto_perps(account: Account) -> list[Perp]:
    return [p for p in account.perps if not p.is_stock]


def apply_legs(account: Account, legs: list[Leg], *, weekend_book: bool = False) -> Account:
    nxt, _ = apply_legs_with_fills(account, legs, weekend_book=weekend_book)
    return nxt


def apply_legs_with_fills(
    account: Account, legs: list[Leg], *, weekend_book: bool = False
) -> tuple[Account, list[Fill]]:
    nxt = account.clone()
    fills: list[Fill] = []
    for leg in legs:
        if leg.kind == "cut_live":
            fill = _cut_perp(nxt, leg.symbol, leg.fraction)
            if fill:
                fills.append(fill)
        elif leg.kind == "convert_collateral":
            fill = _convert(nxt, leg.symbol, leg.fraction, weekend_book=weekend_book)
            if fill:
                fills.append(fill)
    return nxt, fills


def _cut_perp(account: Account, symbol: str, fraction: float) -> Fill | None:
    frac = min(1.0, max(0.0, fraction))
    if frac <= 0:
        return None
    for p in account.perps:
        if p.symbol != symbol:
            continue
        qty = p.qty * frac
        notional = p.notional * frac
        fee = notional * FUTURES_TAKER_FEE
        realized = p.upnl * frac
        cash_delta = realized - fee
        account.cash_usdt += cash_delta
        p.qty *= 1.0 - frac
        side_close = "sell" if p.side == "long" else "buy"
        return Fill(
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            p.symbol,
            side_close,
            p.mark_usd,
            qty,
            cash_delta,
            "cut_live",
        )
    return None


def _convert(account: Account, ticker: str, fraction: float, *, weekend_book: bool = False) -> Fill | None:
    frac = min(1.0, max(0.0, fraction))
    if frac <= 0:
        return None
    for c in account.collaterals:
        if c.ticker != ticker:
            continue
        px = c.live_ref_usd
        if weekend_book and c.cash_close_usd > 0:
            lo = c.cash_close_usd * (1.0 - RTOKEN_WEEKEND_LIMIT_BAND)
            hi = c.cash_close_usd * (1.0 + RTOKEN_WEEKEND_LIMIT_BAND)
            px = min(hi, max(lo, px))
        qty = c.units * frac
        sell = qty * px
        fee = sell * SPOT_TAKER_FEE
        cash_delta = sell - fee
        account.cash_usdt += cash_delta
        c.units *= 1.0 - frac
        return Fill(
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            f"r{c.ticker}",
            "sell",
            px,
            qty,
            cash_delta,
            "convert_collateral",
        )
    return None


def plan_derisk(account: Account, p90_gaps: dict[str, float], *, frozen: bool = True) -> list[Leg]:
    """Cut live crypto first (unbanded). If p90 still fails, sell rToken into USDT."""
    legs: list[Leg] = []
    probe = account.clone()

    def fails(acct: Account) -> bool:
        snap = monday_snapshot(acct, p90_gaps) if frozen else snapshot(acct)
        return _policy_fail(snap)

    cryptos = sorted(_crypto_perps(probe), key=lambda p: p.notional, reverse=True)
    for p in cryptos:
        if not fails(probe):
            break
        best = 0.0
        for step in range(1, 21):
            frac = step / 20.0
            trial = probe.clone()
            _cut_perp(trial, p.symbol, frac)
            if not fails(trial):
                best = frac
                break
            best = frac
        if best > 0:
            legs.append(
                Leg(
                    "cut_live",
                    p.symbol,
                    round(best, 4),
                    f"Cut {p.symbol} by {best:.0%}. Crypto marks are live; this frees IM tonight.",
                )
            )
            _cut_perp(probe, p.symbol, best)

    if fails(probe):
        ranked = sorted(
            probe.collaterals,
            key=lambda c: abs(float(p90_gaps.get(c.ticker, 0.0))),
            reverse=True,
        )
        for c in ranked:
            if c.units <= 0:
                continue
            if not fails(probe):
                break
            best = 0.0
            for step in range(1, 21):
                frac = step / 20.0
                trial = probe.clone()
                _convert(trial, c.ticker, frac)
                if not fails(trial):
                    best = frac
                    break
                best = frac
            if best > 0:
                legs.append(
                    Leg(
                        "convert_collateral",
                        c.ticker,
                        round(best, 4),
                        f"Sell {best:.0%} of r{c.ticker} for USDT so Monday's gap cannot haircut IM.",
                    )
                )
                _convert(probe, c.ticker, best)

    # Stock perps still trade 24/7. Refusing a fake hedge does not mean we cannot close one.
    if fails(probe):
        stocks = sorted([p for p in probe.perps if p.is_stock], key=lambda p: p.im, reverse=True)
        for p in stocks:
            if not fails(probe):
                break
            best = 0.0
            for step in range(1, 21):
                frac = step / 20.0
                trial = probe.clone()
                _cut_perp(trial, p.symbol, frac)
                if not fails(trial):
                    best = frac
                    break
                best = frac
            if best > 0:
                legs.append(
                    Leg(
                        "cut_live",
                        p.symbol,
                        round(best, 4),
                        f"Close {best:.0%} of {p.symbol}. Clamped mark is not cover; IM still has to go.",
                    )
                )
                _cut_perp(probe, p.symbol, best)
    return legs


def decide(account: Account, session: Session, news: News) -> Decision:
    book = gap_book(news)
    p50_g = _percentile_gaps(book, "p50")
    p90_g = _percentile_gaps(book, "p90")
    p99_g = _percentile_gaps(book, "p99")
    screen = snapshot(account)
    p50 = monday_snapshot(account, p50_g)
    p90 = monday_snapshot(account, p90_g)
    p99 = monday_snapshot(account, p99_g)
    fakes = detect_fake_hedges(account, p90_g)

    # Freeze window is Fri 20:00 ET → Mon 9:30 ET. Outside it the index is live:
    # derisk against the screen only, never a fictional Monday cash gap.
    if not session.collateral_index_frozen:
        if not _policy_fail(screen):
            reason = (
                "US cash session — rToken index is live. No frozen-collateral illusion. HOLD."
                if session.kind == "regular"
                else "Cash index is live this session. Book funds IM. HOLD unless a human takes the earnings print."
            )
            action = "HOLD"
            if fakes and session.stock_perp_mark_clamped:
                action = "REFUSE_FAKE_HEDGE"
                reason = (
                    "Stock-perp mark is still clamped to the live index while cash is dark. "
                    "Do not treat it as full cash-gap cover. No size added."
                )
            d = Decision(
                action=action,
                reason=reason,
                fake_hedges=fakes,
                screen=screen,
                p50=p50,
                p90=p90,
                p99=p99,
                news=news,
                session=session,
                gap_book=book,
            )
            d.explanation = explain(d)
            return d
        legs = plan_derisk(account, p90_g, frozen=False)
        nxt = apply_legs(account, legs, weekend_book=False)
        after = snapshot(nxt)
        action = "CUT_LIVE" if any(x.kind == "cut_live" for x in legs) else "CONVERT_COLLATERAL"
        if not legs:
            action = "HOLD"
            reason = "Live index session is already failing, but nothing left to cut."
        else:
            reason = "Live rToken index. Screen fails IM+buffer. Cut live risk; Monday cash gaps are not applied."
        d = Decision(
            action=action,
            reason=reason,
            legs=legs,
            fake_hedges=fakes,
            screen=screen,
            p50=p50,
            p90=p90,
            p99=p99,
            after=after,
            news=news,
            session=session,
            gap_book=book,
        )
        d.explanation = explain(d)
        return d

    if not _policy_fail(p90) and not _policy_fail(screen):
        action = "HOLD"
        reason = "Monday p90 still funds IM plus buffer. Nightshift does nothing."
        if fakes:
            action = "REFUSE_FAKE_HEDGE"
            reason = (
                "Book survives p90, but a stock-perp hedge cannot print the implied cash gap "
                "beyond the index-relative mark clamp until cash reopens. Do not treat it as cover."
            )
        d = Decision(
            action=action,
            reason=reason,
            fake_hedges=fakes,
            screen=screen,
            p50=p50,
            p90=p90,
            p99=p99,
            news=news,
            session=session,
            gap_book=book,
        )
        d.explanation = explain(d)
        return d

    legs = plan_derisk(account, p90_g, frozen=True)
    after = snapshot(apply_legs(account, legs, weekend_book=session.rtoken_weekend_book))
    after_p90 = monday_snapshot(
        apply_legs(account, legs, weekend_book=session.rtoken_weekend_book), p90_g
    )
    action = "CUT_LIVE" if any(x.kind == "cut_live" for x in legs) else "CONVERT_COLLATERAL"
    if not legs:
        action = "HOLD"
        reason = "No live crypto or rToken left to cut. Human must add USDT."
    else:
        reason = (
            "Monday p90 fails the IM+buffer test while the screen still looks funded "
            "because the rToken index is frozen. Cut the live leg first."
        )
        if fakes:
            reason += " A banded NVDA perp is not a substitute for that cut."
            action = "CUT_LIVE" if action == "CUT_LIVE" else action
    d = Decision(
        action=action,
        reason=reason,
        legs=legs,
        fake_hedges=fakes,
        screen=screen,
        p50=p50,
        p90=p90,
        p99=p99,
        after=after_p90,
        news=news,
        session=session,
        gap_book=book,
    )
    # Stash post-trade screen-ish snapshot too
    d.after = after_p90
    d.explanation = explain(d)
    _ = after
    return d


def explain(d: Decision) -> str:
    news = d.news.label if d.news else "none"
    sess = d.session.kind if d.session else "?"
    screen = d.screen
    p90 = d.p90
    lines = []
    lines.append(f"Session: {sess}. News: {news}.")
    if screen:
        lines.append(
            f"Screen: equity ${screen.equity:,.0f}, credit ${screen.collateral_credit:,.0f}, "
            f"resource ${screen.margin_resource:,.0f} vs IM ${screen.im:,.0f} → {screen.status}."
        )
    if p90:
        lines.append(
            f"Monday p90: equity ${p90.equity:,.0f}, credit ${p90.collateral_credit:,.0f}, "
            f"resource ${p90.margin_resource:,.0f} vs IM ${p90.im:,.0f} → {p90.status}."
        )
    if d.fake_hedges:
        lines.append(d.fake_hedges[0].note)
    if d.action == "HOLD":
        lines.append("Kernel: HOLD. Doing nothing is a first-class action.")
    else:
        for leg in d.legs:
            lines.append(f"Kernel: {leg.kind} {leg.symbol} {leg.fraction:.0%}. {leg.note}")
        if not d.legs and d.action == "REFUSE_FAKE_HEDGE":
            lines.append("Kernel: refuse cosmetic hedge. No size change.")
    lines.append(
        f"Policy: resource must cover IM × {1+POLICY_IM_BUFFER:.2f} after p90. "
        "The model cannot raise leverage or open risk."
    )
    return " ".join(lines)

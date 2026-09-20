"""Screen snapshot vs Monday-implied snapshot. Pure math."""

from __future__ import annotations

from dataclasses import dataclass

from nightshift.account import Account
from nightshift.config import (
    POLICY_IM_BUFFER,
    STOCK_PERP_INDEX_MAX_DEV,
    STOCK_PERP_MARK_CLAMP,
    mark_clamp_for,
)


@dataclass
class Snapshot:
    equity: float
    im: float
    mm: float
    collateral_credit: float
    margin_resource: float
    display_ratio: float
    policy_ok: bool
    policy_buffer_ok: bool
    liquidatable_display: bool
    status: str
    display_status: str
    status_why: str
    gaps_applied: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "equity": round(self.equity, 2),
            "im": round(self.im, 2),
            "mm": round(self.mm, 2),
            "collateral_credit": round(self.collateral_credit, 2),
            "margin_resource": round(self.margin_resource, 2),
            "display_ratio": round(self.display_ratio, 2) if self.display_ratio != float("inf") else None,
            "policy_ok": self.policy_ok,
            "policy_buffer_ok": self.policy_buffer_ok,
            "liquidatable_display": self.liquidatable_display,
            "status": self.status,
            "display_status": self.display_status,
            "status_why": self.status_why,
            "gaps_applied": {k: round(v, 4) for k, v in self.gaps_applied.items()},
        }


def _status(resource: float, im: float, equity: float, mm: float) -> tuple[str, str, bool, bool, bool]:
    display_dead = mm > 0 and equity <= mm
    policy_ok = resource + 1e-9 >= im
    buffer_need = im * (1.0 + POLICY_IM_BUFFER)
    policy_buffer_ok = resource + 1e-9 >= buffer_need if im > 0 else True
    if display_dead:
        return "DEAD", "Equity ≤ display maintenance (Bitget-style MMR).", policy_ok, policy_buffer_ok, True
    if im <= 1e-9:
        return "SAFE", "No leveraged perps. Nothing to fund.", True, True, False
    if resource < im:
        return (
            "DEAD",
            "Margin resource cannot fund initial margin once the rToken index is honest.",
            False,
            False,
            False,
        )
    if not policy_buffer_ok:
        return (
            "CALL",
            f"Resource covers IM but not the {int(POLICY_IM_BUFFER*100)}% Nightshift buffer.",
            True,
            False,
            False,
        )
    return "SAFE", "Policy buffer holds.", True, True, False


def snapshot(account: Account, gaps_applied: dict[str, float] | None = None) -> Snapshot:
    mm = account.mm
    equity = account.equity
    im = account.im
    resource = account.margin_resource
    display_ratio = (equity / mm) if mm > 1e-9 else float("inf")
    status, why, policy_ok, buf_ok, disp_dead = _status(resource, im, equity, mm)
    if disp_dead:
        display_status = "DEAD"
    elif mm <= 1e-9 or display_ratio >= 2.0:
        display_status = "SAFE"
    else:
        display_status = "TIGHT"
    return Snapshot(
        equity=equity,
        im=im,
        mm=mm,
        collateral_credit=account.collateral_credit,
        margin_resource=resource,
        display_ratio=display_ratio,
        policy_ok=policy_ok,
        policy_buffer_ok=buf_ok,
        liquidatable_display=disp_dead,
        status=status,
        display_status=display_status,
        status_why=why,
        gaps_applied=gaps_applied or {},
    )


def apply_monday_gaps(account: Account, gaps: dict[str, float]) -> Account:
    """Unfreeze rToken index to cash_close * (1+gap). Unclamp stock-perp marks to the same cash-implied price.

    Crypto perps are left as-is: weekend BTC already sits in live mark/UPNL.
    """
    nxt = account.clone()
    for c in nxt.collaterals:
        gap = float(gaps.get(c.ticker, 0.0))
        nxt_px = c.cash_close_usd * (1.0 + gap)
        c.index_usd = nxt_px
        c.live_ref_usd = nxt_px
    for p in nxt.perps:
        if not p.is_stock:
            continue
        from nightshift.account import perp_to_equity_ticker

        ticker = perp_to_equity_ticker(p.symbol)
        if not ticker:
            continue
        gap = float(gaps.get(ticker, 0.0))
        # Find matching collateral cash close if present; else scale current mark as if unclamped.
        cash_close = None
        for c in account.collaterals:
            if c.ticker == ticker:
                cash_close = c.cash_close_usd
                break
        if cash_close:
            p.mark_usd = cash_close * (1.0 + gap)
        else:
            d = mark_clamp_for(p.symbol)
            p.mark_usd = p.mark_usd / max(1e-9, (1.0 + _clamped(gap, d))) * (1.0 + gap)
    return nxt


def _clamped(gap: float, width: float = STOCK_PERP_MARK_CLAMP) -> float:
    return min(width, max(-width, gap))


def clamp_index_to_external(index: float, cash_close: float) -> float:
    lo = cash_close * (1.0 - STOCK_PERP_INDEX_MAX_DEV)
    hi = cash_close * (1.0 + STOCK_PERP_INDEX_MAX_DEV)
    return min(hi, max(lo, index))


def clamp_mark_to_index(mark: float, index: float, symbol: str) -> float:
    d = mark_clamp_for(symbol)
    return min(index * (1.0 + d), max(index * (1.0 - d), mark))


def monday_snapshot(account: Account, gaps: dict[str, float]) -> Snapshot:
    return snapshot(apply_monday_gaps(account, gaps), gaps_applied=gaps)


def clamp_stock_mark_for_weekend(cash_close: float, implied_gap: float, symbol: str = "NVDAUSDT") -> float:
    """Index-relative weekend mark: cash close as external index, then ±d around that index."""
    index = clamp_index_to_external(cash_close * (1.0 + implied_gap), cash_close)
    return clamp_mark_to_index(index, index, symbol)

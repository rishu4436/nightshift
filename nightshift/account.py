"""UTA snapshot: rToken collateral + perps. Pure math, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from nightshift.config import DEFAULT_COLLATERAL_RATIO, DISPLAY_MMR, UNIVERSE


def perp_to_equity_ticker(symbol: str) -> str | None:
    s = symbol.upper()
    for ticker, name in UNIVERSE.items():
        if name.stock_perp == s:
            return ticker
    return None


def is_stock_perp(symbol: str) -> bool:
    return perp_to_equity_ticker(symbol) is not None


@dataclass
class Collateral:
    ticker: str
    units: float
    index_usd: float  # what Bitget uses for margin (frozen on weekend)
    live_ref_usd: float  # weekend rToken last (indicative)
    cash_close_usd: float  # last cash print
    ratio: float = DEFAULT_COLLATERAL_RATIO
    weekend_spot: bool = True

    @property
    def index_value(self) -> float:
        return self.units * self.index_usd

    @property
    def credit(self) -> float:
        return self.index_value * self.ratio

    @property
    def live_value(self) -> float:
        return self.units * self.live_ref_usd

    def to_dict(self) -> dict:
        d = asdict(self)
        d["index_value"] = round(self.index_value, 4)
        d["credit"] = round(self.credit, 4)
        d["live_value"] = round(self.live_value, 4)
        return d


@dataclass
class Perp:
    symbol: str
    side: str  # long | short
    qty: float
    entry_usd: float
    mark_usd: float
    leverage: float
    is_stock: bool = False

    @property
    def notional(self) -> float:
        return abs(self.qty * self.mark_usd)

    @property
    def upnl(self) -> float:
        sign = 1.0 if self.side == "long" else -1.0
        return sign * self.qty * (self.mark_usd - self.entry_usd)

    @property
    def im(self) -> float:
        if self.leverage <= 0:
            return self.notional
        return self.notional / self.leverage

    def to_dict(self) -> dict:
        d = asdict(self)
        d["notional"] = round(self.notional, 4)
        d["upnl"] = round(self.upnl, 4)
        d["im"] = round(self.im, 4)
        return d


@dataclass
class Account:
    cash_usdt: float = 0.0
    collaterals: list[Collateral] = field(default_factory=list)
    perps: list[Perp] = field(default_factory=list)
    label: str = "paper"

    def clone(self) -> "Account":
        return Account(
            cash_usdt=self.cash_usdt,
            collaterals=[Collateral(**asdict(c)) for c in self.collaterals],
            perps=[Perp(**asdict(p)) for p in self.perps],
            label=self.label,
        )

    @property
    def rtoken_index_value(self) -> float:
        return sum(c.index_value for c in self.collaterals)

    @property
    def collateral_credit(self) -> float:
        return sum(c.credit for c in self.collaterals)

    @property
    def upnl(self) -> float:
        return sum(p.upnl for p in self.perps)

    @property
    def equity(self) -> float:
        return self.cash_usdt + self.rtoken_index_value + self.upnl

    @property
    def im(self) -> float:
        return sum(p.im for p in self.perps)

    @property
    def mm(self) -> float:
        return sum(p.notional * DISPLAY_MMR for p in self.perps)

    @property
    def margin_resource(self) -> float:
        """USDT + haircut collateral + futures PnL. The number that must fund IM."""
        return self.cash_usdt + self.collateral_credit + self.upnl

    def to_dict(self) -> dict:
        return {
            "cash_usdt": round(self.cash_usdt, 4),
            "collaterals": [c.to_dict() for c in self.collaterals],
            "perps": [p.to_dict() for p in self.perps],
            "label": self.label,
            "rtoken_index_value": round(self.rtoken_index_value, 4),
            "collateral_credit": round(self.collateral_credit, 4),
            "upnl": round(self.upnl, 4),
            "equity": round(self.equity, 4),
            "im": round(self.im, 4),
            "mm": round(self.mm, 4),
            "margin_resource": round(self.margin_resource, 4),
        }


def collateral_from_dict(d: dict) -> Collateral:
    return Collateral(
        ticker=d["ticker"],
        units=float(d["units"]),
        index_usd=float(d["index_usd"]),
        live_ref_usd=float(d["live_ref_usd"]),
        cash_close_usd=float(d["cash_close_usd"]),
        ratio=float(d.get("ratio", DEFAULT_COLLATERAL_RATIO)),
        weekend_spot=bool(d.get("weekend_spot", True)),
    )


def perp_from_dict(d: dict) -> Perp:
    return Perp(
        symbol=d["symbol"],
        side=d["side"],
        qty=float(d["qty"]),
        entry_usd=float(d["entry_usd"]),
        mark_usd=float(d["mark_usd"]),
        leverage=float(d["leverage"]),
        is_stock=bool(d.get("is_stock", False)),
    )


def account_from_dict(d: dict) -> Account:
    return Account(
        cash_usdt=float(d.get("cash_usdt", 0.0)),
        collaterals=[collateral_from_dict(c) for c in d.get("collaterals", [])],
        perps=[perp_from_dict(p) for p in d.get("perps", [])],
        label=str(d.get("label") or "paper"),
    )

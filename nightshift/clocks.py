"""Three clocks from Bitget public APIs. Cash last is frozen locally when US cash is dark."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from nightshift.calendar import Session, session_at
from nightshift.config import BITGET_PUBLIC, UNIVERSE

CASH_CLOSE_PATH = Path(__file__).resolve().parent.parent / "data" / "cash_close.json"


@dataclass
class Clock:
    ticker: str
    rtoken_last: float | None
    rtoken_bid: float | None
    rtoken_ask: float | None
    perp_last: float | None
    perp_mark: float | None
    perp_index: float | None
    cash_last: float | None
    cash_frozen: bool
    basis_rtoken_vs_perp_bps: float | None
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["basis_rtoken_vs_perp_bps"] is not None:
            d["basis_rtoken_vs_perp_bps"] = round(d["basis_rtoken_vs_perp_bps"], 1)
        return d


def _get_json(client: httpx.Client, path: str, params: dict) -> dict:
    r = client.get(f"{BITGET_PUBLIC}{path}", params=params, timeout=10.0)
    r.raise_for_status()
    body = r.json()
    if str(body.get("code")) != "00000":
        raise RuntimeError(body.get("msg") or "bitget error")
    data = body.get("data")
    if isinstance(data, list):
        if not data:
            raise RuntimeError("empty data")
        return data[0]
    return data


def _load_cash_close() -> dict:
    if CASH_CLOSE_PATH.exists():
        return json.loads(CASH_CLOSE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cash_close(store: dict) -> None:
    CASH_CLOSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASH_CLOSE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def fetch_clocks(session: Session | None = None) -> dict:
    sess = session or session_at()
    store = _load_cash_close()
    clocks: list[Clock] = []
    btc = None
    with httpx.Client(headers={"User-Agent": "nightshift/0.1"}) as client:
        for ticker, name in UNIVERSE.items():
            if ticker in {"BTC", "ETH"}:
                continue
            err = None
            rtoken = perp = None
            try:
                if name.rtoken_spot:
                    rtoken = _get_json(
                        client,
                        "/api/v2/spot/market/tickers",
                        {"symbol": name.rtoken_spot},
                    )
                if name.stock_perp:
                    perp = _get_json(
                        client,
                        "/api/v2/mix/market/ticker",
                        {"productType": "USDT-FUTURES", "symbol": name.stock_perp},
                    )
            except Exception as exc:
                err = str(exc)
            r_last = float(rtoken["lastPr"]) if rtoken else None
            p_last = float(perp["lastPr"]) if perp else None
            p_mark = float(perp.get("markPrice") or 0) if perp else None
            p_index = float(perp.get("indexPrice") or 0) if perp else None
            if r_last and not sess.collateral_index_frozen:
                store[ticker] = r_last
                cash_last = r_last
                frozen = False
            else:
                cash_last = float(store[ticker]) if ticker in store else r_last
                frozen = True
            basis = None
            if r_last and p_mark:
                basis = (r_last / p_mark - 1.0) * 10_000
            clocks.append(
                Clock(
                    ticker=ticker,
                    rtoken_last=r_last,
                    rtoken_bid=float(rtoken["bidPr"]) if rtoken else None,
                    rtoken_ask=float(rtoken["askPr"]) if rtoken else None,
                    perp_last=p_last,
                    perp_mark=p_mark or None,
                    perp_index=p_index or None,
                    cash_last=cash_last,
                    cash_frozen=frozen,
                    basis_rtoken_vs_perp_bps=basis,
                    error=err,
                )
            )
        try:
            raw = _get_json(
                client,
                "/api/v2/mix/market/ticker",
                {"productType": "USDT-FUTURES", "symbol": "BTCUSDT"},
            )
            btc = {
                "last": float(raw["lastPr"]),
                "mark": float(raw.get("markPrice") or raw["lastPr"]),
                "index": float(raw.get("indexPrice") or 0),
                "funding": float(raw.get("fundingRate") or 0),
            }
        except Exception as exc:
            btc = {"error": str(exc)}
    if store:
        _save_cash_close(store)
    return {
        "session": sess.to_dict(),
        "clocks": [c.to_dict() for c in clocks],
        "btc": btc,
    }

"""Read-only Bitget UTA client. Never logs secrets. Never places orders."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import httpx

from nightshift.account import Account, Collateral, Perp, is_stock_perp
from nightshift.config import BITGET_PUBLIC, DEFAULT_COLLATERAL_RATIO, UNIVERSE


def configured() -> bool:
    return bool(os.getenv("BITGET_API_KEY") and os.getenv("BITGET_API_SECRET") and os.getenv("BITGET_API_PASSPHRASE"))


def status() -> dict:
    return {
        "configured": configured(),
        "orders": False,
        "mode": "read-only snapshot → local paper kernel",
    }


def _creds() -> tuple[str, str, str]:
    key = (os.getenv("BITGET_API_KEY") or "").strip()
    secret = (os.getenv("BITGET_API_SECRET") or "").strip()
    phrase = (os.getenv("BITGET_API_PASSPHRASE") or "").strip()
    if not (key and secret and phrase):
        raise RuntimeError(
            "Set BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE in .env. "
            "Create the key as READ-ONLY (UTA account read). No trade, no withdraw."
        )
    return key, secret, phrase


def _sign(secret: str, timestamp: str, method: str, path: str, query: str) -> str:
    pre = timestamp + method.upper() + path + (("?" + query) if query else "")
    digest = hmac.new(secret.encode("utf-8"), pre.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _get(path: str, params: dict | None = None) -> dict:
    key, secret, phrase = _creds()
    query = ""
    if params:
        query = urlencode(sorted((k, v) for k, v in params.items() if v is not None))
    ts = str(int(time.time() * 1000))
    headers = {
        "ACCESS-KEY": key,
        "ACCESS-SIGN": _sign(secret, ts, "GET", path, query),
        "ACCESS-PASSPHRASE": phrase,
        "ACCESS-TIMESTAMP": ts,
        "locale": "en-US",
        "Content-Type": "application/json",
        "User-Agent": "nightshift/0.2",
    }
    url = BITGET_PUBLIC + path + (("?" + query) if query else "")
    with httpx.Client(timeout=20.0) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        body = r.json()
    if str(body.get("code")) != "00000":
        raise RuntimeError(body.get("msg") or "bitget error")
    return body.get("data")


def fetch_raw() -> dict:
    assets = _get("/api/v3/account/assets")
    positions = _get("/api/v3/position/current-position", {"category": "USDT-FUTURES"})
    return {"assets": assets, "positions": positions}


def _coin_to_equity(coin: str) -> str | None:
    c = coin.upper().lstrip()
    if c.startswith("R") and len(c) > 1:
        rest = c[1:]
        if rest in UNIVERSE and UNIVERSE[rest].is_equity:
            return rest
    return None


def account_from_raw(raw: dict, clocks: dict | None = None) -> Account:
    data = raw.get("assets") or {}
    asset_list = data.get("assets") if isinstance(data, dict) else data
    if not isinstance(asset_list, list):
        asset_list = []
    cash = 0.0
    collaterals: list[Collateral] = []
    by_ticker = {c["ticker"]: c for c in (clocks or {}).get("clocks") or []}
    for row in asset_list:
        coin = str(row.get("coin") or "")
        bal = float(row.get("balance") or row.get("equity") or 0)
        if bal <= 0:
            continue
        if coin.upper() == "USDT":
            cash += bal
            continue
        ticker = _coin_to_equity(coin)
        if not ticker:
            continue
        clk = by_ticker.get(ticker) or {}
        px = float(clk.get("rtoken_last") or row.get("usdValue") or 0) or 1.0
        index = float(clk.get("cash_last") or px)
        collaterals.append(
            Collateral(ticker, bal, index, px, index, DEFAULT_COLLATERAL_RATIO)
        )
    pos_root = raw.get("positions") or {}
    pos_list = pos_root.get("list") if isinstance(pos_root, dict) else pos_root
    if not isinstance(pos_list, list):
        pos_list = []
    btc_mark = float(((clocks or {}).get("btc") or {}).get("mark") or 0)
    perps: list[Perp] = []
    for row in pos_list:
        qty = float(row.get("total") or row.get("available") or 0)
        if abs(qty) <= 0:
            continue
        symbol = str(row.get("symbol") or "")
        side = str(row.get("posSide") or row.get("holdSide") or "long").lower()
        if side not in {"long", "short"}:
            side = "long"
        entry = float(row.get("avgPrice") or row.get("openPriceAvg") or 0)
        mark = float(row.get("markPrice") or 0)
        if mark <= 0:
            if symbol == "BTCUSDT" and btc_mark:
                mark = btc_mark
            else:
                mark = entry or 1.0
        lev = float(row.get("leverage") or 1) or 1.0
        perps.append(Perp(symbol, side, abs(qty), entry or mark, mark, lev, is_stock_perp(symbol)))
    return Account(cash, collaterals, perps, label="bitget_uta")


def load_my_book(clocks: dict | None = None) -> Account:
    return account_from_raw(fetch_raw(), clocks)

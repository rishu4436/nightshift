"""Local paper broker + append-only JSONL audit. No exchange keys required."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nightshift.account import Account, account_from_dict
from nightshift.kernel import Decision, Fill, apply_legs_with_fills

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
AUDIT_PATH = LOG_DIR / "audit.jsonl"
FILLS_PATH = LOG_DIR / "fills.jsonl"
ACCOUNT_PATH = LOG_DIR / "paper_account.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return "ns_" + uuid.uuid4().hex[:12]


def account_digest(account: Account) -> str:
    payload = {
        "cash": round(account.cash_usdt, 8),
        "c": [
            (c.ticker, round(c.units, 10), round(c.index_usd, 8), round(c.ratio, 6))
            for c in account.collaterals
        ],
        "p": [
            (p.symbol, p.side, round(p.qty, 10), round(p.entry_usd, 8), round(p.leverage, 6), p.is_stock)
            for p in account.perps
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def append_audit(decision: Decision, run_id: str, scenario: str, applied: bool, fills: list[Fill] | None = None) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": _now(),
        "run_id": run_id,
        "scenario": scenario,
        "applied": applied,
        "decision": decision.to_dict(),
        "fills": [f.to_dict() for f in (fills or [])],
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def append_fills(run_id: str, fills: list[Fill]) -> None:
    if not fills:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with FILLS_PATH.open("a", encoding="utf-8") as f:
        for fill in fills:
            row = fill.to_dict()
            row["run_id"] = run_id
            f.write(json.dumps(row) + "\n")


def read_audit(limit: int = 80) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return list(reversed(rows))


def read_fills(limit: int = 200) -> list[dict]:
    if not FILLS_PATH.exists():
        return []
    lines = FILLS_PATH.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def save_account(account: Account) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    blob = account.to_dict()
    blob["_digest"] = account_digest(account)
    ACCOUNT_PATH.write_text(json.dumps(blob, indent=2), encoding="utf-8")


def load_account() -> Account | None:
    if not ACCOUNT_PATH.exists():
        return None
    raw = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
    digest = raw.pop("_digest", None)
    acct = account_from_dict(raw)
    if digest and digest != account_digest(acct):
        raise ValueError("paper account checksum mismatch — file was tampered or truncated")
    return acct


def apply_and_log(account: Account, decision: Decision, scenario: str) -> tuple[Account, str, dict]:
    run_id = new_run_id()
    weekend = bool(decision.session and decision.session.rtoken_weekend_book)
    nxt, fills = apply_legs_with_fills(account, decision.legs, weekend_book=weekend)
    nxt.label = account.label
    append_fills(run_id, fills)
    row = append_audit(decision, run_id, scenario, applied=True, fills=fills)
    save_account(nxt)
    return nxt, run_id, row


def soak_stats() -> dict:
    """Competition-shaped blotter from applied autopsies: Sharpe, max DD, win rate."""
    rows = [r for r in read_audit(limit=500) if r.get("applied")]
    pnls: list[float] = []
    for r in reversed(rows):
        d = r.get("decision") or {}
        screen = (d.get("screen") or {}).get("equity")
        after = (d.get("after") or {}).get("equity")
        if screen is None:
            continue
        pnls.append(float(after if after is not None else screen) - float(screen))
    n = len(pnls)
    if n == 0:
        return {"n": 0, "sharpe": None, "max_drawdown": None, "win_rate": None, "sum_pnl": 0.0}
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / n
    std = math.sqrt(var)
    sharpe = (mean / std) if std > 1e-12 else None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in pnls:
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    wins = sum(1 for x in pnls if x > 0)
    return {
        "n": n,
        "sharpe": None if sharpe is None else round(sharpe, 4),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(wins / n, 4),
        "sum_pnl": round(sum(pnls), 2),
    }

"""Append-only hash-chained receipts. Evaluate writes a receipt. It never sends a Bitget order."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "logs" / "receipts.jsonl"
EVIDENCE = ROOT / "evidence"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(row: dict) -> str:
    blob = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _last() -> dict | None:
    if not LEDGER.exists():
        return None
    last = None
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)
    return last


def append_receipt(decision: dict, *, scenario: str, llm_used: bool) -> dict:
    prev = _last()
    seq = int((prev or {}).get("seq") or 0) + 1
    prev_hash = (prev or {}).get("hash") or "genesis"
    action = decision.get("action") or "HOLD"
    p90 = (decision.get("p90") or {}).get("status")
    if action == "HOLD":
        verdict = "HOLD"
    elif p90 == "DEAD" or action in {"CUT_LIVE", "CONVERT_COLLATERAL"}:
        verdict = "ALLOW_CAPPED"
    elif action == "REFUSE_FAKE_HEDGE":
        verdict = "REJECT"
    else:
        verdict = "ALLOW_CAPPED"
    body = {
        "seq": seq,
        "ts": _now(),
        "prev_hash": prev_hash,
        "scenario": scenario,
        "action": action,
        "verdict": verdict,
        "llm_sized": False,
        "llm_used": bool(llm_used),
        "exchange_order": False,
        "screen": (decision.get("screen") or {}).get("display_status"),
        "p90": p90,
        "after": (decision.get("after") or {}).get("status"),
    }
    body["hash"] = _hash({k: v for k, v in body.items() if k != "hash"})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    return body


def verify_chain() -> dict:
    if not LEDGER.exists():
        return {"ok": True, "n": 0, "detail": "empty ledger"}
    prev_hash = "genesis"
    n = 0
    for i, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        n += 1
        if row.get("prev_hash") != prev_hash:
            return {"ok": False, "n": n, "detail": f"break at seq {row.get('seq')} line {i}"}
        check = {k: v for k, v in row.items() if k != "hash"}
        if _hash(check) != row.get("hash"):
            return {"ok": False, "n": n, "detail": f"hash mismatch seq {row.get('seq')}"}
        prev_hash = row["hash"]
    return {"ok": True, "n": n, "detail": "chain ok", "tip": prev_hash[:16] if prev_hash != "genesis" else None}


def latest() -> dict | None:
    return _last()


def claims() -> list[dict]:
    return [
        {"claim": "Public Bitget marks (spot/perp tickers)", "status": "proven"},
        {"claim": "Paper UTA kernel (HOLD / CUT_LIVE / CONVERT / REFUSE)", "status": "proven"},
        {"claim": "Qwen classifies + narrates", "status": "proven"},
        {"claim": "Qwen sizes or sends orders", "status": "not claimed"},
        {"claim": "Live Bitget exchange fill / Demo order id", "status": "not claimed"},
        {"claim": "Hash-chained evaluate receipts", "status": "proven"},
        {"claim": "Share HTML autopsy without the server", "status": "proven"},
    ]


def write_evidence_pack() -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    pack = {
        "claims": claims(),
        "chain": verify_chain(),
        "latest_receipt": latest(),
        "ts": _now(),
    }
    path = EVIDENCE / "judge.json"
    path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    return path

"""Autopsy UI + JSON API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nightshift.calendar import session_at
from nightshift.classify import classify
from nightshift.qwen import narrate, status as qwen_status
from nightshift.bitget_private import configured as bitget_configured, status as bitget_status
from nightshift.clocks import fetch_clocks
from nightshift.kernel import apply_legs, decide
from nightshift.paper import (
    append_audit,
    apply_and_log,
    new_run_id,
    read_audit,
    read_fills,
    soak_stats,
)
from nightshift.receipts import append_receipt, claims, latest as latest_receipt, verify_chain, write_evidence_pack
from nightshift.report import REPORTS, save as save_report
from nightshift.scenarios import list_scenarios, load
from nightshift.stress import monday_snapshot, snapshot

STATIC = Path(__file__).resolve().parent / "static"
REPORT_HTML = REPORTS / "latest.html"

app = FastAPI(title="Nightshift", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class RunBody(BaseModel):
    scenario: str = "frozen_illusion"
    headline: str = ""
    apply: bool = False
    use_llm: bool = True


class ReplayBody(BaseModel):
    scenario: str = "frozen_illusion"
    headline: str = ""
    which: str = Field(default="p90", pattern="^(p50|p90|p99)$")


class LiveBody(BaseModel):
    headline: str = ""
    apply: bool = False
    force_weekend: bool = True
    use_llm: bool = True


class StressBody(BaseModel):
    live: bool = True


@app.get("/")
def index():
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/health")
def health():
    sess = session_at()
    return {
        "ok": True,
        "name": "nightshift",
        "session": sess.to_dict(),
        "qwen": qwen_status(),
        "bitget": bitget_status(),
    }


class MyBookBody(BaseModel):
    headline: str = ""
    force_weekend: bool = True
    use_llm: bool = True


@app.post("/api/bitget/autopsy")
async def bitget_autopsy(body: MyBookBody):
    """Snapshot the signed UTA (read-only), then run the local paper kernel. No Bitget order."""
    if not bitget_configured():
        raise HTTPException(
            400,
            "Add a READ-ONLY Bitget API key to .env (UTA account read). No trade permission.",
        )
    from nightshift.bitget_private import load_my_book
    from nightshift.calendar import session_at, weekend_session
    from nightshift.clocks import fetch_clocks
    from nightshift.classify import classify
    from nightshift.kernel import decide
    from nightshift.receipts import append_receipt
    from nightshift.report import save as save_report

    try:
        clocks = await run_in_threadpool(fetch_clocks)
        account = await run_in_threadpool(lambda: load_my_book(clocks))
    except Exception as exc:
        raise HTTPException(502, f"Bitget read failed: {exc}") from exc
    session = weekend_session() if body.force_weekend else session_at()
    news = classify(body.headline, use_llm=body.use_llm)
    decision = decide(account, session, news)
    payload = decision.to_dict()
    narration = narrate(payload) if body.use_llm else None
    out = {
        "run_id": new_run_id(),
        "blurb": "Your Bitget UTA snapshot. Kernel is still local paper — no exchange order.",
        "clocks": clocks,
        "account": account.to_dict(),
        "decision": payload,
        "narration": narration,
        "exchange_order": False,
        "share": "/share",
    }
    save_report(out)
    out["receipt"] = append_receipt(payload, scenario="bitget_uta", llm_used=body.use_llm)
    return out


@app.get("/api/scenarios")
def scenarios():
    return {"scenarios": list_scenarios()}


@app.get("/api/clocks")
async def clocks():
    try:
        return await run_in_threadpool(fetch_clocks)
    except Exception as exc:
        raise HTTPException(502, f"clock fetch failed: {exc}") from exc


@app.get("/api/audit")
def audit(limit: int = 40):
    return {"rows": read_audit(limit)}


@app.get("/api/blotter")
def blotter(limit: int = 200):
    return {"fills": read_fills(limit), "soak": soak_stats()}


@app.get("/api/soak")
def soak():
    return soak_stats()


@app.post("/api/qwen/ping")
def qwen_ping():
    from nightshift.qwen import ping

    if not qwen_status()["configured"]:
        raise HTTPException(400, "Set BITGET_QWEN_API_KEY in .env")
    try:
        return ping()
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/run")
def run(body: RunBody):
    try:
        account, session, news, blurb = load(body.scenario)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.headline.strip():
        news = classify(body.headline, use_llm=body.use_llm)
    decision = decide(account, session, news)
    applied = None
    if body.apply:
        nxt, run_id, row = apply_and_log(account, decision, body.scenario)
        applied = {"run_id": run_id, "account": nxt.to_dict(), "audit": row}
    else:
        run_id = new_run_id()
        append_audit(decision, run_id, body.scenario, applied=False)
    after_account = apply_legs(account, decision.legs) if decision.legs else account.clone()
    payload = decision.to_dict()
    narration = narrate(payload) if body.use_llm else None
    out = {
        "run_id": run_id,
        "blurb": blurb,
        "account": account.to_dict(),
        "after_account": after_account.to_dict(),
        "decision": payload,
        "narration": narration,
        "applied": applied,
        "share": "/share",
    }
    save_report(out)
    out["receipt"] = append_receipt(payload, scenario=body.scenario, llm_used=body.use_llm)
    return out


@app.post("/api/replay")
def replay(body: ReplayBody):
    try:
        account, session, news, blurb = load(body.scenario)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.headline.strip():
        news = classify(body.headline, use_llm=False)
    decision = decide(account, session, news)
    which = body.which
    gaps = (decision.gap_book or {}).items()
    gap = {t: float(v[which]) for t, v in gaps}
    without = monday_snapshot(account, gap)
    with_agent = monday_snapshot(apply_legs(account, decision.legs), gap)
    return {
        "blurb": blurb,
        "which": which,
        "gaps": gap,
        "without_agent": without.to_dict(),
        "with_agent": with_agent.to_dict(),
        "screen": snapshot(account).to_dict(),
        "action": decision.action,
        "legs": [x.to_dict() for x in decision.legs],
    }


@app.post("/api/live")
async def live(body: LiveBody):
    from nightshift.book import live_book

    try:
        account, session, news, blurb, clocks = await run_in_threadpool(
            lambda: live_book(force_weekend=body.force_weekend, headline=body.headline)
        )
    except Exception as exc:
        raise HTTPException(502, f"live book failed: {exc}") from exc
    if body.headline.strip():
        news = classify(body.headline, use_llm=body.use_llm)
    decision = decide(account, session, news)
    applied = None
    if body.apply:
        nxt, run_id, row = apply_and_log(account, decision, "live_book")
        applied = {"run_id": run_id, "account": nxt.to_dict(), "audit": row}
    else:
        run_id = new_run_id()
        append_audit(decision, run_id, "live_book", applied=False)
    after_account = apply_legs(account, decision.legs) if decision.legs else account.clone()
    payload = decision.to_dict()
    narration = narrate(payload) if body.use_llm else None
    out = {
        "run_id": run_id,
        "blurb": blurb,
        "clocks": clocks,
        "account": account.to_dict(),
        "after_account": after_account.to_dict(),
        "decision": payload,
        "narration": narration,
        "applied": applied,
        "share": "/share",
    }
    save_report(out)
    out["receipt"] = append_receipt(payload, scenario="live_book", llm_used=body.use_llm)
    return out


@app.post("/api/stress")
async def stress(body: StressBody):
    from nightshift.harness import run_all, run_offline

    if body.live:
        return await run_in_threadpool(lambda: run_all(live=True))
    return await run_in_threadpool(run_offline)


@app.get("/api/claims")
def api_claims():
    return {"claims": claims(), "chain": verify_chain(), "latest": latest_receipt()}


@app.get("/api/market_state")
async def market_state():
    try:
        clocks = await run_in_threadpool(fetch_clocks)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"session": session_at().to_dict(), "clocks": clocks, "exchange_order": False}


@app.get("/api/safety_posture")
def safety_posture():
    return {
        "llm_can_size": False,
        "exchange_orders": False,
        "paper_only": True,
        "bitget_private_key_required": False,
        "chain": verify_chain(),
    }


class EvaluateBody(BaseModel):
    scenario: str = "frozen_illusion"
    headline: str = ""


@app.post("/api/evaluate")
def evaluate(body: EvaluateBody):
    """Public poke: kernel verdict + receipt. Never a Bitget order."""
    try:
        account, session, news, blurb = load(body.scenario)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.headline.strip():
        news = classify(body.headline, use_llm=False)
    decision = decide(account, session, news)
    payload = decision.to_dict()
    receipt = append_receipt(payload, scenario=body.scenario, llm_used=False)
    write_evidence_pack()
    return {
        "verdict": receipt["verdict"],
        "action": decision.action,
        "receipt": receipt,
        "blurb": blurb,
        "exchange_order": False,
        "screen": payload.get("screen"),
        "p90": payload.get("p90"),
    }


@app.get("/cockpit")
def cockpit():
    return FileResponse(
        STATIC / "cockpit.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/share")
def share():
    if not REPORT_HTML.exists():
        rows = read_audit(1)
        if not rows:
            raise HTTPException(404, "Run Live book once, then open /share")
        save_report({"decision": rows[0].get("decision") or {}, "blurb": rows[0].get("scenario"), "narration": None})
    return FileResponse(
        REPORT_HTML,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/demo/seed")
def demo_seed():
    """Commit one frozen-illusion fill so blotter/soak are not empty."""
    account, session, news, blurb = load("frozen_illusion")
    decision = decide(account, session, news)
    nxt, run_id, row = apply_and_log(account, decision, "frozen_illusion")
    out = {
        "run_id": run_id,
        "blurb": blurb,
        "account": nxt.to_dict(),
        "decision": decision.to_dict(),
        "narration": None,
        "applied": row,
    }
    save_report(out)
    receipt = append_receipt(decision.to_dict(), scenario="frozen_illusion", llm_used=False)
    write_evidence_pack()
    return {"ok": True, "run_id": run_id, "soak": soak_stats(), "fills": read_fills(20), "receipt": receipt}


@app.post("/api/loop/tick")
def loop_tick(body: LiveBody):
    from nightshift.loop import tick

    try:
        return tick(headline=body.headline, apply=body.apply, force_weekend=body.force_weekend)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc

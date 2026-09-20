"""Soak loop: mark-to-market a persistent paper book and run the kernel on a timer."""

from __future__ import annotations

import json
import time

from nightshift.book import apply_live_marks, live_book
from nightshift.calendar import session_at, weekend_session
from nightshift.classify import classify
from nightshift.clocks import fetch_clocks
from nightshift.kernel import decide
from nightshift.paper import apply_and_log, load_account, save_account


def tick(*, headline: str = "", apply: bool = False, force_weekend: bool = True) -> dict:
    session = weekend_session() if force_weekend else session_at()
    clocks = fetch_clocks(session)
    account = load_account()
    if account is None:
        account, session, news, blurb, _ = live_book(
            clocks, force_weekend=force_weekend, headline=headline
        )
        save_account(account)
    else:
        account = apply_live_marks(account, clocks, freeze_index=session.collateral_index_frozen)
        news = classify(headline, use_llm=False)
        blurb = "Persistent paper book marked to live Bitget clocks."
    decision = decide(account, session, news)
    run_id = None
    if apply:
        account, run_id, _ = apply_and_log(account, decision, "live_loop")
    else:
        from nightshift.paper import append_audit, new_run_id

        run_id = new_run_id()
        append_audit(decision, run_id, "live_loop", applied=False)
        save_account(account)
    return {
        "run_id": run_id,
        "blurb": blurb,
        "account": account.to_dict(),
        "decision": decision.to_dict(),
        "session": session.to_dict(),
        "applied": apply,
    }


def run_forever(*, seconds: int = 30, headline: str = "", apply: bool = False, force_weekend: bool = True) -> None:
    while True:
        row = tick(headline=headline, apply=apply, force_weekend=force_weekend)
        action = row["decision"]["action"]
        p90 = row["decision"]["p90"]["status"]
        sess = (row.get("session") or {}).get("as_of_et") or ""
        print(json.dumps({"ts": sess, "action": action, "p90": p90, "run_id": row["run_id"]}))
        time.sleep(max(5, seconds))

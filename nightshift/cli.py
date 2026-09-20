"""CLI: run a scenario, start the demo, or append a live paper tick."""

from __future__ import annotations

import argparse
import json
import sys

from nightshift.classify import classify
from nightshift.clocks import fetch_clocks
from nightshift.kernel import decide
from nightshift.paper import append_audit, apply_and_log, new_run_id, read_audit
from nightshift.scenarios import SCENARIOS, load


def cmd_run(args: argparse.Namespace) -> int:
    account, session, news, blurb = load(args.scenario)
    if args.headline:
        news = classify(args.headline, use_llm=not args.no_llm)
    decision = decide(account, session, news)
    run_id = new_run_id()
    if args.apply:
        _, run_id, _ = apply_and_log(account, decision, args.scenario)
    else:
        append_audit(decision, run_id, args.scenario, applied=False)
    out = {
        "run_id": run_id,
        "blurb": blurb,
        "decision": decision.to_dict(),
    }
    print(json.dumps(out, indent=2))
    print(f"\n{decision.action}: {decision.reason}", file=sys.stderr)
    return 0


def cmd_clocks(_: argparse.Namespace) -> int:
    print(json.dumps(fetch_clocks(), indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    print(json.dumps(read_audit(args.limit), indent=2))
    return 0


def cmd_scenarios(_: argparse.Namespace) -> int:
    from nightshift.scenarios import list_scenarios

    print(json.dumps(list_scenarios(), indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_paper_tick(args: argparse.Namespace) -> int:
    """One loop iteration against a named scenario (for overnight JSONL)."""
    account, session, news, _ = load(args.scenario)
    if args.live_session:
        from nightshift.calendar import session_at

        session = session_at()
    decision = decide(account, session, news)
    _, run_id, _ = apply_and_log(account, decision, args.scenario)
    print(json.dumps({"run_id": run_id, "action": decision.action, "reason": decision.reason}))
    return 0


def cmd_stress(args: argparse.Namespace) -> int:
    from nightshift.harness import run_all, run_offline

    report = run_offline() if args.offline else run_all(live=True)
    print(json.dumps(report, indent=2))
    print(f"\n{report['passed']}/{report['total']} passed, {report['failed']} failed", file=sys.stderr)
    return 0 if report["ok"] else 1


def cmd_live(args: argparse.Namespace) -> int:
    from nightshift.book import live_book
    from nightshift.kernel import decide
    from nightshift.paper import apply_and_log, new_run_id, append_audit, save_account

    account, session, news, blurb, _ = live_book(
        force_weekend=not args.real_session, headline=args.headline
    )
    if args.headline:
        news = classify(args.headline, use_llm=not args.no_llm)
    decision = decide(account, session, news)
    if args.apply:
        _, run_id, _ = apply_and_log(account, decision, "live_book")
    else:
        run_id = new_run_id()
        append_audit(decision, run_id, "live_book", applied=False)
        save_account(account)
    print(json.dumps({"run_id": run_id, "blurb": blurb, "decision": decision.to_dict()}, indent=2))
    print(f"\n{decision.action}: {decision.reason}", file=sys.stderr)
    return 0


def cmd_judge(_: argparse.Namespace) -> int:
    import subprocess

    from nightshift.receipts import verify_chain, write_evidence_pack, claims

    py = sys.executable
    tests = subprocess.run([py, "-m", "pytest", "-q"], cwd=".")
    stress = subprocess.run([py, "-m", "nightshift", "stress", "--offline"], cwd=".")
    chain = verify_chain()
    pack = write_evidence_pack()
    print(json.dumps({
        "pytest": tests.returncode == 0,
        "stress": stress.returncode == 0,
        "chain": chain,
        "claims": claims(),
        "evidence": str(pack),
        "verified": tests.returncode == 0 and stress.returncode == 0 and chain.get("ok"),
    }, indent=2))
    return 0 if tests.returncode == 0 and chain.get("ok") else 1


def cmd_bitget(_: argparse.Namespace) -> int:
    from nightshift.bitget_private import configured, fetch_raw, load_my_book

    if not configured():
        print("No Bitget key. Add READ-ONLY BITGET_API_KEY/SECRET/PASSPHRASE to .env.", file=sys.stderr)
        return 1
    raw = fetch_raw()
    acct = load_my_book()
    coins = [a.get("coin") for a in ((raw.get("assets") or {}).get("assets") or []) if float(a.get("balance") or 0) > 0]
    print(json.dumps({
        "ok": True,
        "coins": coins,
        "cash_usdt": round(acct.cash_usdt, 2),
        "collaterals": [c.ticker for c in acct.collaterals],
        "perps": [p.symbol for p in acct.perps],
        "orders": False,
    }, indent=2))
    return 0


def cmd_qwen(_: argparse.Namespace) -> int:
    from nightshift.qwen import ping, status

    st = status()
    if not st["configured"]:
        print("No key. Put BITGET_QWEN_API_KEY in .env (see .env.example).", file=sys.stderr)
        print(json.dumps(st, indent=2))
        return 1
    try:
        print(json.dumps({**st, **ping()}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({**st, "ok": False, "error": str(exc)}, indent=2))
        return 1


def cmd_loop(args: argparse.Namespace) -> int:
    from nightshift.loop import run_forever, tick

    if args.once:
        print(json.dumps(tick(headline=args.headline, apply=args.apply, force_weekend=not args.real_session), indent=2))
        return 0
    run_forever(
        seconds=args.seconds,
        headline=args.headline,
        apply=args.apply,
        force_weekend=not args.real_session,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nightshift", description="Monday-implied UTA risk kernel")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run a scenario through the kernel")
    r.add_argument("scenario", choices=sorted(SCENARIOS))
    r.add_argument("--headline", default="")
    r.add_argument("--apply", action="store_true")
    r.add_argument("--no-llm", action="store_true")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("clocks", help="Fetch live Bitget three-clock tape")
    c.set_defaults(func=cmd_clocks)

    a = sub.add_parser("audit", help="Print recent JSONL")
    a.add_argument("--limit", type=int, default=20)
    a.set_defaults(func=cmd_audit)

    s = sub.add_parser("scenarios")
    s.set_defaults(func=cmd_scenarios)

    w = sub.add_parser("serve", help="Open the autopsy UI")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8080)
    w.add_argument("--reload", action="store_true")
    w.set_defaults(func=cmd_serve)

    t = sub.add_parser("paper-tick", help="Append one paper decision")
    t.add_argument("scenario", choices=sorted(SCENARIOS))
    t.add_argument("--live-session", action="store_true")
    t.set_defaults(func=cmd_paper_tick)

    st = sub.add_parser("stress", help="Run the full stress harness")
    st.add_argument("--offline", action="store_true", help="Skip live clocks and klines")
    st.set_defaults(func=cmd_stress)

    lv = sub.add_parser("live", help="Autopsy a paper book marked to live Bitget prices")
    lv.add_argument("--headline", default="")
    lv.add_argument("--apply", action="store_true")
    lv.add_argument("--no-llm", action="store_true")
    lv.add_argument("--real-session", action="store_true", help="Do not force weekend freeze")
    lv.set_defaults(func=cmd_live)

    jg = sub.add_parser("judge", help="Two-minute verify pack: tests + stress + receipt chain")
    jg.set_defaults(func=cmd_judge)

    bg = sub.add_parser("bitget", help="Read-only ping of your Bitget UTA (no orders)")
    bg.set_defaults(func=cmd_bitget)

    q = sub.add_parser("qwen", help="Ping Qwen 3.8 Max with the key in .env")
    q.set_defaults(func=cmd_qwen)

    lp = sub.add_parser("loop", help="Soak: mark-to-market and decide on an interval")
    lp.add_argument("--seconds", type=int, default=30)
    lp.add_argument("--headline", default="")
    lp.add_argument("--apply", action="store_true")
    lp.add_argument("--once", action="store_true")
    lp.add_argument("--real-session", action="store_true")
    lp.set_defaults(func=cmd_loop)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

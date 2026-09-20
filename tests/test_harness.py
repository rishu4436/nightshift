from nightshift.harness import run_offline
from nightshift.kernel import apply_legs, decide
from nightshift.scenarios import load


def test_offline_stress_passes():
    report = run_offline()
    failed = [c for c in report["cases"] if not c["ok"]]
    assert report["ok"], failed


def test_double_long_converts_or_cuts_stock():
    account, session, news, _ = load("double_long")
    d = decide(account, session, news)
    kinds = {leg.kind for leg in d.legs}
    assert "cut_live" in kinds
    after = apply_legs(account, d.legs)
    assert after.im < account.im


def test_scenario_cards_have_titles():
    from nightshift.scenarios import list_scenarios

    rows = list_scenarios()
    assert all(r.get("title") and r.get("kicker") for r in rows)


def test_checksum_rejects_tamper():
    from nightshift.paper import load_account, save_account
    from nightshift.scenarios import frozen_illusion
    import json
    from nightshift.paper import ACCOUNT_PATH

    acct, _, _, _ = frozen_illusion()
    save_account(acct)
    blob = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
    blob["cash_usdt"] = 42
    ACCOUNT_PATH.write_text(json.dumps(blob), encoding="utf-8")
    try:
        load_account()
        assert False, "tamper should raise"
    except ValueError:
        pass
    save_account(acct)


def test_empty_holds():
    account, session, news, _ = load("empty_book")
    d = decide(account, session, news)
    assert d.action == "HOLD"
    assert d.legs == []

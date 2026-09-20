from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)


def test_health_and_home():
    h = client.get("/api/health")
    assert h.status_code == 200 and h.json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200
    assert b"NIGHTSHIFT" in page.content
    assert b"Run autopsy" in page.content
    assert b"scene-list" in page.content
    assert page.headers.get("cache-control", "").startswith("no-store")


def test_frozen_illusion_endpoint():
    r = client.post("/api/run", json={"scenario": "frozen_illusion", "apply": False, "use_llm": False})
    assert r.status_code == 200
    d = r.json()["decision"]
    assert d["action"] == "CUT_LIVE"
    assert d["screen"]["display_status"] == "SAFE"
    assert d["p90"]["status"] == "DEAD"


def test_evaluate_is_receipt_not_an_order():
    r = client.post("/api/evaluate", json={"scenario": "frozen_illusion"})
    assert r.status_code == 200
    body = r.json()
    assert body["exchange_order"] is False
    assert body["action"] == "CUT_LIVE"
    assert body["receipt"]["hash"]
    assert body["receipt"]["llm_sized"] is False


def test_evaluate_quiet_hold():
    r = client.post("/api/evaluate", json={"scenario": "quiet_hold"})
    assert r.status_code == 200
    assert r.json()["action"] == "HOLD"
    assert r.json()["verdict"] == "HOLD"


def test_cockpit_page():
    page = client.get("/cockpit")
    assert page.status_code == 200
    assert b"Judge cockpit" in page.content


def test_share_report_after_run():
    r = client.post("/api/run", json={"scenario": "frozen_illusion", "apply": False, "use_llm": False})
    assert r.status_code == 200
    page = client.get("/share")
    assert page.status_code == 200
    assert b"NIGHTSHIFT" in page.content
    assert b"CUT_LIVE" in page.content or b"SAFE" in page.content


def test_demo_seed_writes_fills():
    r = client.post("/api/demo/seed")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    blot = client.get("/api/blotter").json()
    assert blot["fills"]


def test_replay_saves_the_account():
    r = client.post("/api/replay", json={"scenario": "frozen_illusion", "which": "p90"})
    assert r.status_code == 200
    body = r.json()
    assert body["without_agent"]["status"] == "DEAD"
    assert body["with_agent"]["status"] == "SAFE"

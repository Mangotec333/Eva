"""FastAPI endpoint tests — focus on the separated /summary dashboard payload.

Skipped automatically if Starlette's TestClient HTTP deps are unavailable.
"""

import pytest

pytest.importorskip("starlette")
try:
    from starlette.testclient import TestClient  # noqa: F401  (import check)
except Exception:  # pragma: no cover - httpx missing
    pytest.skip("starlette TestClient unavailable", allow_module_level=True)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import store
    monkeypatch.setitem(store.DB_PATHS, "personal", str(tmp_path / "p.db"))
    monkeypatch.setitem(store.DB_PATHS, "business", str(tmp_path / "b.db"))
    from starlette.testclient import TestClient
    import main
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["module"] == "eva-treasurer"


def test_ingest_and_summary_sections_are_separate(client):
    assert client.post("/personal/ingest", json={"provider": "mock"}).status_code == 200
    assert client.post("/business/ingest", json={"provider": "mock"}).status_code == 200

    body = client.get("/summary").json()
    assert set(body["personal"]) >= {"side", "accounts", "budget", "utilization"}
    assert body["personal"]["side"] == "personal"
    assert body["business"]["side"] == "business"

    p_insts = {a["institution"] for a in body["personal"]["accounts"]}
    b_insts = {a["institution"] for a in body["business"]["accounts"]}
    assert p_insts == {"Chase", "Amex"}
    assert b_insts == {"Mercury", "Chase Ink"}
    assert p_insts.isdisjoint(b_insts)


def test_invalid_side_rejected(client):
    assert client.get("/household/accounts").status_code == 400


def test_utilization_endpoint(client):
    client.post("/personal/ingest", json={"provider": "mock"})
    r = client.get("/personal/utilization", params={"threshold": 0.30})
    assert r.status_code == 200
    # Personal Amex Gold: 420000/1000000 = 42% => one alert.
    assert r.json()["alert_count"] == 1

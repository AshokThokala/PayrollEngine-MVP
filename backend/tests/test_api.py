"""HTTP API tests. Skipped automatically when FastAPI is not installed."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app, get_service  # noqa: E402

OPS = {"X-User": "ops1"}
REVIEWER = {"X-User": "reviewer"}


@pytest.fixture()
def client():
    get_service.cache_clear()
    return TestClient(app)


def test_full_month_flow(client):
    assert client.post("/clients", json={"id": "acme", "legal_name": "Acme", "state": "TG"},
                       headers=OPS).status_code == 201
    r = client.post("/clients/acme/employees", headers=OPS, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01",
        "components": {"basic": 15000, "hra": 6000, "special_allowance": 4000}})
    assert r.status_code == 201 and r.json()["warnings"] == []

    run = client.post("/clients/acme/runs", headers=OPS, json={"period": "2026-10-01"}).json()
    assert run["status"] == "draft" and float(run["total_net"]) == 23000
    assert [r["id"] for r in client.get("/clients/acme/runs").json()] == ["acme:2026-10"]
    assert client.get("/runs/acme%3A2026-10").json()["id"] == "acme:2026-10"

    assert client.post(f"/runs/{run['id']}/approve", headers=OPS).status_code == 409
    assert client.post(f"/runs/{run['id']}/approve", headers=REVIEWER).status_code == 200
    filings = client.post(f"/runs/{run['id']}/lock", headers=REVIEWER).json()
    assert {f["kind"] for f in filings} == {"pf", "tds_deposit", "pt"}

    pf = next(f for f in filings if f["kind"] == "pf")
    r = client.post(f"/filings/{pf['id']}", headers=OPS, json={"status": "paid", "challan_ref": "TRRN1"})
    assert r.json()["status"] == "paid"
    overdue = client.get("/filings", params={"overdue_on": "2026-11-20"}).json()
    assert {f["kind"] for f in overdue} == {"tds_deposit", "pt"}


def test_errors(client):
    assert client.get("/runs/nope").status_code == 404
    assert client.post("/clients", json={"id": "x1", "legal_name": "X", "state": "KA"},
                       headers=OPS).status_code == 409
    assert client.post("/clients", json={"id": "x1", "legal_name": "X"}).status_code == 422

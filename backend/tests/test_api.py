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


def test_errors_name_the_field(client):
    r = client.post("/clients", headers=OPS, json={"id": "Bad ID", "legal_name": ""})
    assert r.status_code == 422
    fields = {e["field"]: e["label"] for e in r.json()["errors"]}
    assert fields == {"id": "Client ID", "legal_name": "Legal name"}
    assert r.json()["detail"].startswith("Client ID: ")

    client.post("/clients", headers=OPS, json={"id": "acme", "legal_name": "Acme"})
    r = client.post("/clients", headers=OPS, json={"id": "acme", "legal_name": "Acme again"})
    assert r.status_code == 409 and r.json()["errors"][0]["label"] == "Client ID"

    r = client.post("/clients/acme/employees", headers=OPS, json={
        "code": "E1", "name": "Ravi", "joined_on": "not-a-date", "components": {"basic": -5}})
    labels = {e["label"] for e in r.json()["errors"]}
    assert labels == {"Joined on", "Monthly salary – Basic"}

    r = client.post("/clients", json={"id": "x2", "legal_name": "X"})
    assert r.json()["errors"][0]["label"] == "Acting as"


def test_rules_endpoints(client):
    cats = {c["category"]: c for c in client.get("/rules/categories").json()}
    assert cats["pf"]["scope"] == "central" and cats["lwf"]["scope"] == "state"
    states = {s["code"]: s["supported"] for s in client.get("/rules/states").json()}
    assert states["TG"] is True and states["KA"] is False

    pf = client.get("/rules", params={"category": "pf"}).json()
    assert [r["valid_from"] for r in pf] == ["2014-09-01", "2026-09-17"]

    body = {"scope": "KA", "category": "lwf", "valid_from": "2026-01-01", "source": "test",
            "params": {"employee_amount": 20, "employer_amount": 40, "deduction_months": [12],
                       "due_month": 1, "due_day": 15}}
    r = client.post("/rules", headers=OPS, json=body)
    assert r.status_code == 201 and r.json()["closed"] is None
    assert {s["code"]: s["supported"] for s in client.get("/rules/states").json()}["KA"] is True

    bad = {**body, "valid_from": "2027-01-01", "params": {**body["params"], "due_day": 0}, "source": ""}
    r = client.post("/rules", headers=OPS, json=bad)
    assert r.status_code == 422
    labels = {e["label"] for e in r.json()["errors"]}
    assert labels == {"Payment due day", "Source"}

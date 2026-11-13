"""HTTP API tests. Skipped automatically when FastAPI is not installed."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app, get_auth, get_service  # noqa: E402

PASSWORD = "Passw0rd1"


@pytest.fixture()
def client():
    get_service.cache_clear()
    get_auth.cache_clear()
    c = TestClient(app)
    auth = get_auth()
    auth.create_platform_admin("ops1@cp.in", PASSWORD, "Ops One")
    auth.create_platform_admin("reviewer@cp.in", PASSWORD, "Reviewer")
    return c


def login(c, email, password=PASSWORD):
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.json()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def ops(client):
    return login(client, "ops1@cp.in")


@pytest.fixture()
def reviewer(client):
    return login(client, "reviewer@cp.in")


def test_full_month_flow(client, ops, reviewer):
    assert client.post("/clients", json={"id": "acme", "legal_name": "Acme", "state": "TG"},
                       headers=ops).status_code == 201
    r = client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01",
        "components": {"basic": 15000, "hra": 6000, "special_allowance": 4000}})
    assert r.status_code == 201 and r.json()["warnings"] == []

    run = client.post("/clients/acme/runs", headers=ops, json={"period": "2026-10-01"}).json()
    assert run["status"] == "draft" and float(run["total_net"]) == 23000
    assert [r["id"] for r in client.get("/clients/acme/runs", headers=ops).json()] == ["acme:2026-10"]
    assert client.get("/runs/acme%3A2026-10", headers=ops).json()["id"] == "acme:2026-10"

    assert client.post(f"/runs/{run['id']}/approve", headers=ops).status_code == 200  # preparer may approve
    filings = client.post(f"/runs/{run['id']}/lock", headers=reviewer).json()
    assert {f["kind"] for f in filings} == {"pf", "tds_deposit", "pt"}

    pf = next(f for f in filings if f["kind"] == "pf")
    r = client.post(f"/filings/{pf['id']}", headers=ops, json={"status": "paid", "challan_ref": "TRRN1"})
    assert r.json()["status"] == "paid"
    overdue = client.get("/filings", params={"overdue_on": "2026-11-20"}, headers=ops).json()
    assert {f["kind"] for f in overdue} == {"tds_deposit", "pt"}


def test_errors(client, ops, reviewer):
    assert client.get("/runs/nope", headers=ops).status_code == 404
    assert client.post("/clients", json={"id": "x1", "legal_name": "X", "state": "KA"},
                       headers=ops).status_code == 409
    assert client.post("/clients", json={"id": "x1", "legal_name": "X"}).status_code == 401  # not logged in


def test_errors_name_the_field(client, ops, reviewer):
    r = client.post("/clients", headers=ops, json={"id": "Bad ID", "legal_name": ""})
    assert r.status_code == 422
    fields = {e["field"]: e["label"] for e in r.json()["errors"]}
    assert fields == {"id": "Client ID", "legal_name": "Legal name"}
    assert r.json()["detail"].startswith("Client ID: ")

    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme"})
    r = client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme again"})
    assert r.status_code == 409 and r.json()["errors"][0]["label"] == "Client ID"

    r = client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "not-a-date", "components": {"basic": -5}})
    labels = {e["label"] for e in r.json()["errors"]}
    assert labels == {"Joined on", "Monthly salary – Basic"}

    r = client.post("/clients", json={"id": "x2", "legal_name": "X"})
    assert r.status_code == 401 and r.json()["detail"] == "Please log in"


def test_rules_endpoints(client, ops, reviewer):
    cats = {c["category"]: c for c in client.get("/rules/categories").json()}
    assert cats["pf"]["scope"] == "central" and cats["lwf"]["scope"] == "state"
    states = {s["code"]: s["supported"] for s in client.get("/rules/states").json()}
    assert states["TG"] is True and states["KA"] is False

    pf = client.get("/rules", params={"category": "pf"}, headers=ops).json()
    assert [r["valid_from"] for r in pf] == ["2014-09-01", "2026-09-17"]

    body = {"scope": "KA", "category": "lwf", "valid_from": "2026-01-01", "source": "test",
            "params": {"employee_amount": 20, "employer_amount": 40, "deduction_months": [12],
                       "due_month": 1, "due_day": 15}}
    r = client.post("/rules", headers=ops, json=body)
    assert r.status_code == 201 and r.json()["closed"] is None
    assert {s["code"]: s["supported"] for s in client.get("/rules/states").json()}["KA"] is True

    bad = {**body, "valid_from": "2027-01-01", "params": {**body["params"], "due_day": 0}, "source": ""}
    r = client.post("/rules", headers=ops, json=bad)
    assert r.status_code == 422
    labels = {e["label"] for e in r.json()["errors"]}
    assert labels == {"Payment due day", "Source"}


def test_edit_rule_and_tax_profile(client, ops, reviewer):
    pt = client.get("/rules", params={"scope": "TG", "category": "professional_tax"}, headers=ops).json()[0]
    r = client.put(f"/rules/{pt['id']}", headers=ops,
                   json={"params": {**pt["params"], "due_day": 12}, "source": "Corrected"})
    assert r.status_code == 200 and r.json()["params"]["due_day"] == 12
    r = client.put(f"/rules/{pt['id']}", headers=ops, json={"params": {**pt["params"], "due_day": 0}, "source": ""})
    assert r.status_code == 422 and {e["label"] for e in r.json()["errors"]} == {"Due day (next month)", "Source"}
    assert client.put("/rules/central:pf:1999-01-01", headers=ops, json={"params": {}, "source": "x"}).status_code == 404

    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme"})
    r = client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01",
        "components": {"basic": 50000, "hra": 20000, "special_allowance": 30000},
        "tax": {"tax_regime": "old", "metro_city": True, "declarations": {"sec_80c": 150000}}})
    assert r.status_code == 201 and r.json()["employee"]["tax"]["tax_regime"] == "old"
    r = client.put("/clients/acme/employees/E1/tax", headers=ops,
                   json={"tax_regime": "old", "tax_age_group": "elder", "declarations": {"rent_paid": -5}})
    assert r.status_code == 422
    assert {e["label"] for e in r.json()["errors"]} == {"Age group", "Rent paid (₹/year)"}



def test_roles_and_self_service(client, ops, reviewer):
    # A business signs up and is logged in straight away
    r = client.post("/auth/signup/client", json={
        "client": {"id": "acme", "legal_name": "Acme", "state": "TG"},
        "name": "Asha", "email": "asha@acme.in", "password": "Payroll123"})
    assert r.status_code == 201 and r.json()["user"]["client_id"] == "acme"
    asha = {"Authorization": f"Bearer {r.json()['token']}"}
    client.post("/auth/signup/client", json={
        "client": {"id": "beta", "legal_name": "Beta", "state": "TG"},
        "name": "Bala", "email": "bala@beta.in", "password": "Payroll123"})

    # Client admin sees only their own client
    assert [c["id"] for c in client.get("/clients", headers=asha).json()] == ["acme"]
    assert client.get("/clients/beta/employees", headers=asha).status_code == 403
    assert client.post("/clients", headers=asha, json={"id": "gamma", "legal_name": "G"}).status_code == 403
    assert client.post("/rules", headers=asha, json={"scope": "TG", "category": "lwf", "valid_from": "2027-01-01",
                                                     "params": {}, "source": "x"}).status_code == 403

    client.post("/clients/acme/employees", headers=asha, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01", "components": {"basic": 30000}})

    # Employee signs up -> pending -> approved by the client admin
    r = client.post("/auth/signup/employee", json={"client_id": "acme", "employee_code": "E1",
                                                   "name": "Ravi", "email": "ravi@x.in", "password": "Ravi12345"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    r = client.post("/auth/login", json={"email": "ravi@x.in", "password": "Ravi12345"})
    assert r.status_code == 409 and "approval" in r.json()["detail"]
    pending = [u for u in client.get("/users", headers=asha).json() if u["status"] == "pending"]
    assert client.post(f"/users/{pending[0]['id']}/approve", headers=asha).json()["status"] == "active"
    ravi = login(client, "ravi@x.in", "Ravi12345")

    # Employee: own data only
    assert client.get("/me/employee", headers=ravi).json()["employee"]["code"] == "E1"
    assert client.get("/clients", headers=ravi).status_code == 403
    assert client.get("/clients/acme/employees", headers=ravi).status_code == 403
    run = client.post("/clients/acme/runs", headers=asha, json={"period": "2026-10-01"}).json()
    assert client.get("/me/payslips", headers=ravi).json() == []  # drafts hidden
    client.post(f"/runs/{run['id']}/approve", headers=ops)
    client.post(f"/runs/{run['id']}/lock", headers=ops)
    slips = client.get("/me/payslips", headers=ravi).json()
    assert [p["payslip"]["employee_code"] for p in slips] == ["E1"]
    r = client.put("/me/tax", headers=ravi, json={"tax_regime": "old", "declarations": {"sec_80c": 40000}})
    assert r.json()["tax"]["tax_regime"] == "old"

    # Wrong password and bad sign-up fields name the field
    assert client.post("/auth/login", json={"email": "asha@acme.in", "password": "nope"}).status_code == 409
    r = client.post("/auth/signup/employee", json={"client_id": "acme", "employee_code": "E1",
                                                   "name": "X", "email": "bad", "password": "x"})
    assert r.status_code == 409 and r.json()["errors"][0]["label"] == "Employee code"


def test_reports_edit_and_view_as(client, ops, reviewer):
    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme"})
    client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01", "components": {"basic": 30000}})
    run = client.post("/clients/acme/runs", headers=ops, json={"period": "2026-10-01"}).json()
    client.post(f"/runs/{run['id']}/approve", headers=reviewer)
    client.post(f"/runs/{run['id']}/lock", headers=reviewer)

    assert {r["key"] for r in client.get("/reports", headers=ops).json()} >= {"salary_register", "cost_trend"}
    reg = client.get("/clients/acme/reports/salary_register", params={"month": "2026-10-01"}, headers=ops).json()
    assert reg["rows"][0]["code"] == "E1" and reg["columns"][0]["key"] == "code"
    assert client.get("/clients/acme/reports/nope", headers=ops).status_code == 404

    r = client.put("/clients/acme", headers=ops, json={"legal_name": "Acme Textiles", "pan": "AAACA1234A"})
    assert r.json()["legal_name"] == "Acme Textiles"
    r = client.put("/clients/acme/employees/E1", headers=ops,
                   json={"name": "Ravi Kumar", "flags": {"pt_applicable": False}})
    assert r.json()["employee"]["name"] == "Ravi Kumar" and r.json()["employee"]["flags"]["pt_applicable"] is False

    r = client.post("/clients/acme/employees/E1/view-as", headers=ops)
    assert r.json()["user"]["impersonated_by"] == "ops1@cp.in"
    viewer = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/me/employee", headers=viewer).json()["employee"]["code"] == "E1"
    assert len(client.get("/me/payslips", headers=viewer).json()) == 1
    assert client.put("/me/tax", headers=viewer, json={"tax_regime": "old"}).status_code == 403
    assert client.get("/clients", headers=viewer).status_code == 403


def test_onboarding_and_billing_api(client, ops, reviewer):
    r = client.post("/auth/signup/client", json={"client": {"id": "acme", "legal_name": "Acme", "state": "TG"},
                                                  "name": "Asha", "email": "asha@acme.in", "password": "Payroll123"})
    asha = {"Authorization": f"Bearer {r.json()['token']}"}
    check = client.get("/clients/acme/onboarding", headers=asha).json()
    assert check["total"] == 7 and {s["key"]: s["done"] for s in check["steps"]}["admin"] is True
    assert client.get("/onboarding/clients", headers=asha).status_code == 403
    assert client.get("/onboarding/clients", headers=ops).json()[0]["client_id"] == "acme"

    assert client.put("/clients/acme/billing/plan", headers=asha, json={"plan": "managed"}).status_code == 403
    plan = client.put("/clients/acme/billing/plan", headers=ops, json={"plan": "managed"}).json()
    assert float(plan["minimum_fee"]) == 5000
    client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01", "components": {"basic": 30000}})
    run = client.post("/clients/acme/runs", headers=ops, json={"period": "2026-10-01"}).json()
    client.post(f"/runs/{run['id']}/approve", headers=reviewer)
    client.post(f"/runs/{run['id']}/lock", headers=reviewer)
    inv = client.post("/clients/acme/invoices", headers=ops, json={"month": "2026-10-01"}).json()
    assert inv["status"] == "draft"
    assert client.get("/clients/acme/billing", headers=asha).json()["invoices"] == []  # drafts hidden
    issued = client.post(f"/invoices/{inv['id']}/issue", headers=ops).json()
    assert issued["number"].startswith("CP4U/")
    seen = client.get("/clients/acme/billing", headers=asha).json()["invoices"]
    assert [i["number"] for i in seen] == [issued["number"]]
    r = client.post(f"/invoices/{inv['id']}/pay", headers=ops, json={"paid_on": "2026-11-10", "reference": ""})
    assert r.status_code == 409 and r.json()["errors"][0]["label"] == "Payment reference"
    paid = client.post(f"/invoices/{inv['id']}/pay", headers=ops, json={"paid_on": "2026-11-10", "reference": "UTR1"})
    assert paid.json()["status"] == "paid"
    assert client.get("/billing/overview", headers=ops).status_code == 200


def test_employee_invite_and_onboarding_api(client, ops):
    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme", "state": "TG"})
    client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01", "components": {"basic": 30000}})
    inv = client.post("/clients/acme/employees/E1/invite", headers=ops, json={"email": "ravi@acme.in"})
    assert inv.status_code == 201 and inv.json()["path"].startswith("/invite/")
    assert inv.json()["email_sent"] is False and inv.json()["email_error"]  # no SMTP server in tests
    token = inv.json()["path"].split("/")[-1]
    assert client.get(f"/invite/{token}").json()["employee_name"] == "Ravi"
    r = client.post(f"/invite/{token}/accept", json={"name": "Ravi K", "password": "short"})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "password"
    r = client.post(f"/invite/{token}/accept", json={"name": "Ravi K", "password": "Payroll123"})
    assert r.status_code == 201
    ravi = {"Authorization": f"Bearer {r.json()['token']}"}

    r = client.put("/me/onboarding", headers=ravi, json={"phone": "123", "submit": True})
    assert r.status_code == 422
    labels = {e["field"]: e["label"] for e in r.json()["errors"]}
    assert labels["phone"] == "Mobile number" and labels["account_number"] == "Bank account number"
    good = {"phone": "9876543210", "date_of_birth": "1995-06-15", "address": "Road 1", "city": "Hyderabad",
            "pincode": "500034", "emergency_name": "L", "emergency_phone": "9123456780", "bank_name": "HDFC",
            "ifsc": "HDFC0001234", "pan": "ABCDE1234F", "account_number": "50100012345678", "submit": True}
    assert client.put("/me/onboarding", headers=ravi, json=good).json()["status"] == "submitted"
    rows = client.get("/clients/acme/employee-onboarding", headers=ops).json()
    assert rows[0]["stage"] == "submitted"
    assert client.get("/clients/acme/employees/E1/profile", headers=ravi).status_code == 403
    assert client.get("/clients/acme/employees/E1/profile", headers=ops).json()["pan"] == "ABCDE1234F"
    assert client.post("/clients/acme/employees/E1/profile/verify", headers=ops).json()["status"] == "verified"
    assert client.get("/me/onboarding", headers=ravi).json()["status"] == "verified"

def test_tax_rules_api(client, ops):
    o = client.get("/tax/rules?on=2026-11-10", headers=ops).json()
    assert o["tax_year"] == "2026-27" and o["regimes"]["new"]["params"]["rebate_max"] == 60000
    r = client.post("/tax/calculate", headers=ops, json={"annual_gross": "1500000"})
    assert r.status_code == 200 and r.json()["better"] in ("new", "old")
    r = client.post("/tax/calculate", headers=ops, json={"annual_gross": "x"})
    assert r.status_code == 422 and r.json()["errors"][0]["label"] == "Yearly gross salary"
    assert client.get("/tax/rules").status_code == 401


def test_search_api(client, ops):
    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme", "state": "TG"})
    client.post("/clients/acme/employees", headers=ops, json={
        "code": "E1", "name": "Ravi", "joined_on": "2026-04-01", "components": {"basic": 30000}})
    r = client.get("/search?q=rav", headers=ops).json()
    assert r["employees"][0]["code"] == "E1" and r["employees"][0]["active"] is True
    assert client.get("/search?q=acm", headers=ops).json() == {"query": "acm", "employees": []}
    assert client.get("/search?q=ra").status_code == 401


def test_add_user_api(client, ops):
    client.post("/clients", headers=ops, json={"id": "acme", "legal_name": "Acme", "state": "TG"})
    r = client.post("/users", headers=ops, json={"name": "Ravi", "email": "ravi@acme.in",
                                                 "password": "Payroll123", "client_id": "acme"})
    assert r.status_code == 201 and r.json()["client_id"] == "acme" and r.json()["status"] == "active"
    r = client.post("/users", headers=ops, json={"name": "", "email": "bad", "password": "x"})
    assert r.status_code == 422 and {e["field"] for e in r.json()["errors"]} == {"name", "email", "password"}
    assert client.post("/users", json={"name": "A", "email": "a@b.in", "password": "Payroll123"}).status_code == 401

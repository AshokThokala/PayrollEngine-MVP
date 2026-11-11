"""Billing plans, invoices with GST, and the client onboarding checklist."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain import Client, EmployeeRecord, InvoiceStatus
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError
from app.services.billing import BillingService
from app.services.onboarding import all_clients, client_checklist

D = Decimal


def setup(repo, state="TG", employees=3):
    svc = PayrollService(repo, clock=lambda: datetime(2026, 11, 5, tzinfo=timezone.utc))
    svc.ensure_rules_seeded()
    svc.add_client(Client(id="acme", legal_name="Acme", state=state), "ops")
    for i in range(employees):
        svc.add_employee(EmployeeRecord("acme", Employee(code=f"E{i}", name=f"E{i}"),
                                        SalaryStructure({"basic": 20000}), date(2026, 4, 1)), "ops")
    return svc, BillingService(svc)


def lock(svc, month):
    run = svc.create_draft("acme", date(2026, month, 1), user="ops")
    svc.approve(run.id, "rev")
    svc.lock(run.id, "rev")


def test_plan_defaults_and_validation(repo):
    svc, b = setup(repo)
    plan = b.set_plan("acme", "ops", plan="managed")
    assert (plan.rate_per_employee, plan.minimum_fee, plan.onboarding_fee) == (D(150), D(5000), D(15000))
    plan = b.set_plan("acme", "ops", plan="software", rate_per_employee="55")
    assert plan.rate_per_employee == D(55) and plan.onboarding_fee == 0
    with pytest.raises(ServiceError) as exc:
        b.set_plan("acme", "ops", plan="software", minimum_fee=-1, billing_email="nope")
    assert set(exc.value.errors) == {"minimum_fee", "billing_email"}
    with pytest.raises(ServiceError):
        b.set_plan("acme", "ops", plan="gold")


def test_invoice_minimum_onboarding_and_gst_same_state(repo):
    svc, b = setup(repo)
    b.set_plan("acme", "ops", plan="managed")
    with pytest.raises(ServiceError, match="Lock"):
        b.generate("acme", date(2026, 10, 1), "ops")
    lock(svc, 10)
    inv = b.generate("acme", date(2026, 10, 1), "ops")
    # 3 × 150 = 450, top-up to 5,000, plus 15,000 onboarding = 20,000; GST 18% split CGST/SGST
    assert [l["amount"] for l in inv.lines] == ["450.00", "4550.00", "15000.00"]
    assert (inv.subtotal, inv.cgst, inv.sgst, inv.igst, inv.total) == (D(20000), D(1800), D(1800), D(0), D(23600))
    issued = b.issue(inv.id, "ops")
    assert issued.number == "CP4U/2026-27/0001" and issued.due_date == date(2026, 11, 20)
    with pytest.raises(ServiceError):
        b.generate("acme", date(2026, 10, 1), "ops")  # already issued
    lock(svc, 9)
    nov = b.generate("acme", date(2026, 9, 1), "ops")
    assert all(l["description"] != "One-time onboarding" for l in nov.lines)  # charged once
    assert b.issue(nov.id, "ops").number == "CP4U/2026-27/0002"
    with pytest.raises(ServiceError, match="reference"):
        b.mark_paid(issued.id, "ops", date(2026, 11, 10), " ")
    paid = b.mark_paid(issued.id, "ops", date(2026, 11, 10), "UTR123")
    assert paid.status == InvoiceStatus.PAID
    with pytest.raises(ServiceError):
        b.void(paid.id, "ops")
    assert b.void(nov.id, "ops").number == "CP4U/2026-27/0002"  # number stays used
    rows = b.overview(date(2026, 12, 1))
    assert rows[0]["outstanding"] == 0


def test_igst_for_other_state(repo, monkeypatch):
    monkeypatch.setenv("PROVIDER_STATE", "KA")
    svc, b = setup(repo, employees=40)
    b.set_plan("acme", "ops", plan="software")
    lock(svc, 10)
    inv = b.generate("acme", date(2026, 10, 1), "ops")
    assert (inv.subtotal, inv.cgst, inv.igst, inv.total) == (D(2400), D(0), D(432), D(2832))


def test_onboarding_checklist_follows_the_data(repo):
    svc, b = setup(repo, employees=0)
    first = client_checklist(svc, "acme")
    assert first["done"] == 0 and first["next_step"] == "Company details" and not first["live"]
    svc.update_client("acme", {"pan": "AAACA1234A", "tan": "HYDA12345B", "pf_code": "TSHYD1",
                               "pt_registration": "36123"}, "ops")
    from app.auth import hash_password
    from app.domain import Role, User
    repo.save_user(User("u1", "asha@acme.in", "Asha", Role.ADMIN, hash_password("x"), client_id="acme"))
    b.set_plan("acme", "ops", plan="managed")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                    SalaryStructure({"basic": 8000, "special_allowance": 12000}), date(2026, 4, 1)), "ops")
    mid = client_checklist(svc, "acme")
    status = {s["key"]: s["done"] for s in mid["steps"]}
    assert status == {"company": True, "registrations": True, "admin": True, "billing": True,
                      "employees": True, "salaries": False, "first_run": False}
    assert "E1" in next(s for s in mid["steps"] if s["key"] == "salaries")["detail"]
    svc.update_employee("acme", "E1", "ops", components={"basic": 12000, "special_allowance": 8000})
    lock(svc, 10)
    done = client_checklist(svc, "acme")
    assert done["live"] and done["percent"] == 100
    assert all_clients(svc)[0]["client_id"] == "acme"

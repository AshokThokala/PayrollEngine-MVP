"""Deduction master and standing employee deductions in payroll runs."""
from datetime import date
from decimal import Decimal

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, Role, User
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError
from app.services.auth_service import AccessDenied
from app.services.deductions import DeductionService

OPS = User("p", "ops@cp.in", "Ops", Role.ADMIN, hash_password("x"))
ACME = User("a", "asha@acme.in", "Asha", Role.ADMIN, hash_password("x"), client_id="acme")


@pytest.fixture
def svc(repo):
    s = PayrollService(repo)
    s.ensure_rules_seeded()
    s.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops")
    s.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                  SalaryStructure({"basic": 30000, "hra": 12000, "special_allowance": 8000}),
                                  date(2026, 4, 1)), "ops")
    ds = DeductionService(s)
    for code in ("vpf", "loan_emi", "canteen", "nps_employee"):
        ds.set_client(OPS, "acme", code, {"enabled": True})
    return s


def test_master_is_seeded_once(svc, repo):
    ds = DeductionService(svc)
    codes = {t.code: t for t in ds.types()}
    assert {"pf_employee", "tds", "vpf", "nps_employee", "loan_emi", "salary_advance"} <= set(codes)
    assert codes["pf_employee"].category.value == "statutory" and codes["vpf"].tax_section == "80C"
    ds.save_type(OPS, {"name": "VPF (extra PF)", "category": "voluntary", "default_value": "8"}, code="vpf")
    svc.ensure_rules_seeded()  # seeding again never overwrites edits
    assert repo.get_deduction_type("vpf").name == "VPF (extra PF)"


def test_add_and_edit_types(svc):
    ds = DeductionService(svc)
    t = ds.save_type(OPS, {"code": "gym", "name": "Gym membership", "category": "voluntary", "calc": "fixed",
                           "max_amount": "2000", "payslip_label": "Gym"})
    assert t.code == "gym" and not t.system and t.max_amount == Decimal(2000)
    with pytest.raises(ServiceError) as e:
        ds.save_type(OPS, {"code": "gym", "name": "", "category": "statutory", "calc": "statutory",
                           "tax_section": "99Z"})
    assert set(e.value.errors) == {"type_code", "name", "category", "calc", "tax_section"}
    with pytest.raises(AccessDenied):
        ds.save_type(ACME, {"code": "x1", "name": "X", "category": "voluntary", "calc": "fixed"})
    # Statutory: only wording changes; cannot be switched off or recalculated.
    pf = ds.save_type(OPS, {"name": "EPF", "payslip_label": "PF", "active": False, "calc": "fixed"},
                      code="pf_employee")
    assert pf.name == "EPF" and pf.active and pf.calc.value == "statutory"
    # Shipped non-statutory types keep their calculation.
    assert ds.save_type(OPS, {"name": "VPF", "category": "voluntary", "calc": "fixed"}, code="vpf").calc.value \
        == "percent_basic"


def test_employee_deductions_flow_into_payroll(svc):
    ds = DeductionService(svc)
    ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "vpf", "value": "10", "start_month": "2026-10"})
    ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "loan_emi", "value": "2500",
                                              "start_month": "2026-09", "end_month": "2026-10"})
    ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "canteen", "value": "600",
                                              "start_month": "2026-12"})
    oct_ = {d.code: d for d in svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"].deductions}
    assert oct_["vpf"].amount == Decimal("3000.00") and oct_["vpf"].label == "VPF"
    assert oct_["loan_emi"].amount == Decimal("2500.00") and "canteen" not in oct_
    nov = {d.code for d in svc.create_draft("acme", date(2026, 11, 1), user="ops").slips["E1"].deductions}
    assert "loan_emi" not in nov and "vpf" in nov  # loan ended in October


def test_one_off_amount_replaces_standing_and_cap(svc):
    ds = DeductionService(svc)
    ds.save_type(OPS, {"code": "gym", "name": "Gym", "category": "voluntary", "calc": "percent_gross",
                       "max_amount": "1000"})
    ds.set_client(OPS, "acme", "gym", {"enabled": True})
    ds.save_for_employee(OPS, "acme", "E1", {"deduction_code": "gym", "value": "5", "start_month": "2026-10"})
    ds.save_for_employee(OPS, "acme", "E1", {"deduction_code": "canteen", "value": "600", "start_month": "2026-10"})
    from app.services.payroll_service import MonthInput
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops",
                           inputs={"E1": MonthInput(other_deductions={"canteen": Decimal(150)})})
    ded = {d.code: d.amount for d in run.slips["E1"].deductions}
    assert ded["gym"] == Decimal("1000.00")  # 5% of 50,000 = 2,500, capped at 1,000
    assert ded["canteen"] == Decimal("150.00")


def test_employee_deduction_validation(svc):
    ds = DeductionService(svc)
    with pytest.raises(ServiceError) as e:
        ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "pf_employee", "value": "-1",
                                                  "start_month": "2026-03", "end_month": "2026-01"})
    assert set(e.value.errors) == {"deduction_code", "value", "start_month", "end_month"}
    with pytest.raises(ServiceError) as e:
        ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "vpf", "value": "150", "start_month": "2026-10"})
    assert "percentage" in e.value.errors["value"]
    d = ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "nps_employee", "start_month": "2026-10"})
    assert d.value == Decimal(10)  # default from the master
    ds.delete_for_employee(ACME, "acme", "E1", d.id)
    assert ds.for_employee("acme", "E1") == []


def test_client_level_controls_employee_deductions(svc):
    ds = DeductionService(svc)
    rows = {r["type"].code: r for r in ds.client_settings("acme")}
    assert rows["pf_employee"]["statutory"] and rows["pf_employee"]["enabled"]
    assert rows["vpf"]["enabled"] and not rows["salary_advance"]["enabled"]
    with pytest.raises(ServiceError) as e:  # not switched on for the client
        ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "salary_advance", "value": "1000",
                                                  "start_month": "2026-10"})
    assert "Client deductions" in e.value.errors["deduction_code"]
    with pytest.raises(ServiceError):
        ds.set_client(OPS, "acme", "pf_employee", {"enabled": False})

    # Client's own default, cap and payslip name.
    ds.set_client(ACME, "acme", "salary_advance", {"enabled": True, "default_value": "2000", "max_amount": "1500",
                                                   "payslip_label": "Advance (Acme)"})
    d = ds.save_for_employee(ACME, "acme", "E1", {"deduction_code": "salary_advance", "start_month": "2026-10"})
    assert d.value == Decimal(2000)
    slip = svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"]
    line = next(x for x in slip.deductions if x.code == "salary_advance")
    assert line.amount == Decimal("1500.00") and line.label == "Advance (Acme)"
    assert ds.client_settings("acme")[0]  # still listable
    assert next(r for r in ds.client_settings("acme") if r["type"].code == "salary_advance")["employees"] == 1

    # Switching it off for the client stops it in later runs.
    ds.set_client(ACME, "acme", "salary_advance", {"enabled": False})
    slip = svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"]
    assert "salary_advance" not in {x.code for x in slip.deductions}
    with pytest.raises(ServiceError) as e:
        ds.set_client(ACME, "acme", "vpf", {"enabled": True, "default_value": "150"})
    assert "percentage" in e.value.errors["default_value"]
    assert len(ds.for_client("acme")) == 1

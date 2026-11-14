"""Pay codes at master, client and employee level."""
from datetime import date
from decimal import Decimal

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, Role, User
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError
from app.services.auth_service import AccessDenied
from app.services.payroll_service import MonthInput
from app.services.paycodes import PayCodeService, client_pay_codes

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
    return s


def test_master_seeded_and_core_codes_on_for_clients(svc, repo):
    pc = PayCodeService(svc)
    codes = {p.code: p for p in pc.codes()}
    assert {"basic", "hra", "lta", "statutory_bonus", "arrears"} <= set(codes)
    assert codes["hra"].tax.value == "partly_exempt" and codes["hra"].tax_section == "10(13A)"
    assert pc.wage_codes() == {"basic", "da", "retaining_allowance"}
    on = client_pay_codes(repo, "acme")
    assert {"basic", "da", "hra", "special_allowance", "conveyance"} <= set(on) and "lta" not in on


def test_master_edit_rules(svc):
    pc = PayCodeService(svc)
    p = pc.save_code(OPS, {"code": "night_allowance", "name": "Night allowance", "kind": "fixed"})
    assert p.kind.value == "fixed" and not p.system
    with pytest.raises(ServiceError) as e:
        pc.save_code(OPS, {"code": "night_allowance", "name": "", "kind": "x", "calc": "percent_basic",
                           "default_value": "150"})
    assert {"type_code", "name", "kind"} <= set(e.value.errors)
    with pytest.raises(ServiceError):
        pc.save_code(OPS, {"name": "Basic", "active": False}, code="basic")
    with pytest.raises(AccessDenied):
        pc.save_code(ACME, {"code": "x1", "name": "X", "kind": "fixed"})


def test_salary_must_use_client_pay_codes(svc):
    pc = PayCodeService(svc)
    with pytest.raises(ServiceError, match="Client pay codes"):
        pc.set_employee_pay(ACME, "acme", "E1", {"basic": "30000", "lta": "2000"})
    pc.set_client(ACME, "acme", "lta", {"enabled": True, "payslip_label": "Leave travel"})
    pc.set_employee_pay(ACME, "acme", "E1", {"basic": "30000", "hra": "12000", "lta": "2000"})
    slip = svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"]
    lines = {l.code: l for l in slip.earnings}
    assert lines["lta"].label == "Leave travel" and lines["hra"].label == "HRA"
    assert lines["lta"].amount == Decimal("2000.00")
    # Can't switch off a pay code employees still have; basic is always on.
    with pytest.raises(ServiceError) as e:
        pc.set_client(ACME, "acme", "lta", {"enabled": False})
    assert "E1" in e.value.errors["enabled"]
    with pytest.raises(ServiceError):
        pc.set_client(ACME, "acme", "basic", {"enabled": False})


def test_variable_pay_in_runs(svc):
    pc = PayCodeService(svc)
    with pytest.raises(ServiceError, match="variable pay"):
        svc.create_draft("acme", date(2026, 10, 1), user="ops",
                         inputs={"E1": MonthInput(other_earnings={"performance_bonus": Decimal(5000)})})
    pc.set_client(OPS, "acme", "performance_bonus", {"enabled": True})
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops",
                           inputs={"E1": MonthInput(other_earnings={"performance_bonus": Decimal(5000)})})
    line = next(l for l in run.slips["E1"].earnings if l.code == "performance_bonus")
    assert line.label == "Performance bonus" and line.amount == Decimal("5000.00")


def test_client_settings_and_grid(svc):
    pc = PayCodeService(svc)
    rows = {r["code"].code: r for r in pc.client_settings("acme")}
    assert rows["basic"]["locked"] and rows["hra"]["employees"] == 1 and not rows["lta"]["enabled"]
    pc.set_client(ACME, "acme", "hra", {"enabled": True, "default_value": "50"})
    assert client_pay_codes(svc.repo, "acme")["hra"].default_value == Decimal(50)
    with pytest.raises(ServiceError):
        pc.set_client(ACME, "acme", "hra", {"enabled": True, "default_value": "150"})
    grid = pc.employee_grid("acme")
    assert grid["employees"][0]["total"] == Decimal(50000)
    assert "hra" in {p.code for p in grid["pay_codes"]} and "performance_bonus" not in {p.code for p in grid["pay_codes"]}

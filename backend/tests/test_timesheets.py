"""Time entry for salaried and hourly employees, and how it flows into payroll."""
from datetime import date
from decimal import Decimal

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, Role, User
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError
from app.services.timesheets import TimeService

OPS = User("p", "ops@cp.in", "Ops", Role.ADMIN, hash_password("x"))


@pytest.fixture
def svc(repo):
    s = PayrollService(repo)
    s.ensure_rules_seeded()
    s.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops")
    s.add_employee(EmployeeRecord("acme", Employee(code="S1", name="Salaried"),
                                  SalaryStructure({"basic": 31200, "special_allowance": 10000}),
                                  date(2026, 4, 1)), "ops")
    s.add_employee(EmployeeRecord("acme", Employee(code="H1", name="Hourly", pay_type="hourly", hourly_rate=200),
                                  SalaryStructure({}), date(2026, 4, 1)), "ops")
    return s


def earn(slip, code):
    return next((l.amount for l in slip.earnings if l.code == code), Decimal(0))


def test_hourly_employee_needs_a_rate(svc):
    with pytest.raises(ServiceError) as e:
        svc.add_employee(EmployeeRecord("acme", Employee(code="H2", name="X", pay_type="hourly"),
                                        SalaryStructure({}), date(2026, 4, 1)), "ops")
    assert e.value.field == "hourly_rate"


def test_salaried_absence_and_overtime(svc):
    ts = TimeService(svc)
    # 2 absent days, 1 half day, 4 OT hours. October has 31 days -> 31 - 2.5 = 28.5 paid days.
    ts.save(OPS, "acme", "S1", "2026-10", {"5": {"status": "A"}, "6": {"status": "A"}, "7": {"status": "HD"},
                                           "8": {"status": "P", "hours": 8, "ot": 4}})
    view = {e["code"]: e for e in ts.month_view("acme", "2026-10")["employees"]}
    assert view["S1"]["lop_days"] == Decimal("2.5") and view["S1"]["paid_days"] == Decimal("28.5")
    # OT rate: 31,200 / 26 / 8 = 150 an hour, x2 = 300; 4 h = 1,200
    assert view["S1"]["ot_rate"] == Decimal("300.00") and view["S1"]["ot_pay"] == Decimal("1200.00")
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops")
    slip = run.slips["S1"]
    assert earn(slip, "basic") == Decimal("28683.87")  # 31,200 x 28.5 / 31
    assert earn(slip, "overtime") == Decimal("1200.00")
    assert "S1: time sheet not approved yet" in run.flags


def test_hourly_pay_from_hours(svc):
    ts = TimeService(svc)
    days = {str(d): {"hours": 8} for d in range(1, 21)}  # 160 hours
    days["21"] = {"hours": 8, "ot": 2}
    ts.save(OPS, "acme", "H1", "2026-10", days, approve=True)
    view = {e["code"]: e for e in ts.month_view("acme", "2026-10")["employees"]}
    assert view["H1"]["regular_hours"] == 168 and view["H1"]["hourly_pay"] == Decimal("33600.00")
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops")
    slip = run.slips["H1"]
    assert earn(slip, "basic") == Decimal("33600.00") and earn(slip, "overtime") == Decimal("800.00")  # 2 h x 400
    assert slip.earnings[0].label.startswith("Wages (168 h")
    assert not any(f.startswith("H1:") and "approved" in f for f in run.flags)


def test_hourly_without_hours_is_flagged(svc):
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops")
    assert "H1: hourly employee with no hours entered" in run.flags
    assert run.slips["S1"].earnings[0].amount == Decimal("31200.00")  # no sheet: full month


def test_validation_and_lock(svc):
    ts = TimeService(svc)
    with pytest.raises(ServiceError) as e:
        ts.save(OPS, "acme", "S1", "2026-10", {"32": {"status": "P"}, "3": {"status": "X"},
                                               "4": {"hours": 20, "ot": 6}, "5": {"status": "A", "hours": 8}})
    assert {"days", "day_3", "day_4", "day_5"} <= set(e.value.errors)
    ts.save(OPS, "acme", "S1", "2026-10", {"1": {"status": "P"}})
    assert ts.approve(OPS, "acme", "2026-10") == 1
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops")
    svc.approve(run.id, user="ops")
    with pytest.raises(ServiceError, match="already approved"):
        ts.save(OPS, "acme", "S1", "2026-10", {"1": {"status": "A"}})


def test_switch_to_hourly(svc):
    svc.update_employee("acme", "S1", "ops", pay_type="hourly", hourly_rate="250")
    e = svc.repo.get_employee("acme", "S1").employee
    assert e.pay_type == "hourly" and e.hourly_rate == Decimal(250)
    with pytest.raises(ServiceError):
        svc.update_employee("acme", "S1", "ops", pay_type="weekly")

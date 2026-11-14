"""Client locations and where employees work (PT and LWF follow the location's state)."""
from datetime import date
from decimal import Decimal

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, Role, User
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError
from app.services.locations import LocationService

OPS = User("p", "ops@cp.in", "Ops", Role.ADMIN, hash_password("x"))
KA_PT = {"slabs": [{"upto": 24999, "amount": 0}, {"upto": None, "amount": 200}], "due_day": 20}


@pytest.fixture
def svc(repo):
    s = PayrollService(repo)
    s.ensure_rules_seeded()
    s.add_client(Client(id="acme", legal_name="Acme", state="TG", pt_registration="tgpt1"), "ops")
    s.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                  SalaryStructure({"basic": 30000, "special_allowance": 20000}), date(2026, 4, 1)), "ops")
    return s


def pt(slip):
    return next((d.amount for d in slip.deductions if d.code == "pt"), Decimal(0))


def test_head_office_made_from_client(svc, repo):
    ls = LocationService(svc)
    rows = ls.locations("acme")
    assert len(rows) == 1 and rows[0]["location"].head_office and rows[0]["location"].state == "TG"
    assert rows[0]["location"].pt_registration == "tgpt1" and rows[0]["employees"] == 1
    assert repo.get_employee("acme", "E1").employee.location_id == rows[0]["location"].id


def test_add_branch_and_validation(svc):
    ls = LocationService(svc)
    with pytest.raises(ServiceError) as e:
        ls.save(OPS, "acme", {"name": "", "state": "KA", "pincode": "012"})
    assert {"name", "state", "pincode"} <= set(e.value.errors)
    assert "Compliance rules" in e.value.errors["state"]
    b = ls.save(OPS, "acme", {"name": "Warangal plant", "state": "tg", "pincode": "506002"})
    assert b.state == "TG" and not b.head_office
    with pytest.raises(ServiceError) as e:
        ls.save(OPS, "acme", {"name": "warangal PLANT", "state": "TG"})
    assert "already" in e.value.errors["name"]
    # Making the branch the head office moves the flag.
    ls.save(OPS, "acme", {"name": "Warangal plant", "state": "TG", "head_office": True}, b.id)
    heads = [r["location"].name for r in ls.locations("acme") if r["location"].head_office]
    assert heads == ["Warangal plant"]


def test_employee_in_other_state_pays_that_states_pt(svc, repo):
    svc.add_rule("KA", "professional_tax", date(2026, 4, 1), KA_PT, "Karnataka PT", "ops")
    ls = LocationService(svc)
    blr = ls.save(OPS, "acme", {"name": "Bengaluru branch", "state": "KA", "city": "Bengaluru"})
    svc.update_employee("acme", "E1", "ops", components={"basic": 12000, "special_allowance": 10000})  # ₹22,000
    assert pt(svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"]) == Decimal("200.00")  # TG: > 20,000
    svc.update_employee("acme", "E1", "ops", location_id=blr.id)
    e = repo.get_employee("acme", "E1").employee
    assert e.location_id == blr.id and e.state == "KA"
    assert pt(svc.create_draft("acme", date(2026, 10, 1), user="ops").slips["E1"]) == Decimal("0")  # KA: under 25,000
    # A location with employees can't be switched off.
    with pytest.raises(ServiceError) as err:
        ls.save(OPS, "acme", {"name": "Bengaluru branch", "state": "KA", "active": False}, blr.id)
    assert "employee" in err.value.errors["active"]


def test_new_employee_at_a_location(svc, repo):
    ls = LocationService(svc)
    plant = ls.save(OPS, "acme", {"name": "Plant", "state": "TG"})
    svc.add_employee(EmployeeRecord("acme", Employee(code="E2", name="Priya", location_id=plant.id),
                                    SalaryStructure({"basic": 30000}), date(2026, 4, 1)), "ops")
    assert repo.get_employee("acme", "E2").employee.location_id == plant.id
    with pytest.raises(ServiceError) as e:
        svc.add_employee(EmployeeRecord("acme", Employee(code="E3", name="X", location_id="nope"),
                                        SalaryStructure({"basic": 30000}), date(2026, 4, 1)), "ops")
    assert e.value.field == "location_id"

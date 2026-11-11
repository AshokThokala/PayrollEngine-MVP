"""Main-screen search for clients and employees."""
from datetime import date

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, Role, User
from app.engine import Employee, SalaryStructure
from app.services import PayrollService
from app.services.auth_service import AccessDenied
from app.services.search import search


@pytest.fixture
def svc(repo):
    s = PayrollService(repo)
    s.ensure_rules_seeded()
    s.add_client(Client(id="acme", legal_name="Acme Textiles", state="TG", pan="AAACA1234A"), "ops")
    s.add_client(Client(id="bharat", legal_name="Bharat Foods", state="TG"), "ops")
    people = [("acme", "E1", "Ravi Kumar"), ("acme", "E2", "Priya_Rao"), ("bharat", "B1", "Ravindra Shah"),
              ("bharat", "B2", "Anil 100%")]
    for cid, code, name in people:
        s.add_employee(EmployeeRecord(cid, Employee(code=code, name=name), SalaryStructure({"basic": 20000}),
                                      date(2026, 4, 1)), "ops")
    return s


PLATFORM = User("p", "ops@cp.in", "Ops", Role.ADMIN, hash_password("x"))
ACME = User("a", "asha@acme.in", "Asha", Role.ADMIN, hash_password("x"), client_id="acme")


def test_platform_admin_sees_all(svc):
    r = search(svc, PLATFORM, "ravi")
    assert [(e["client_id"], e["code"]) for e in r["employees"]] == [("acme", "E1"), ("bharat", "B1")]
    assert r["employees"][1]["client_name"] == "Bharat Foods"
    assert [c["id"] for c in search(svc, PLATFORM, "foods")["clients"]] == ["bharat"]
    assert [c["id"] for c in search(svc, PLATFORM, "aaaca")["clients"]] == ["acme"]  # by PAN
    assert [e["code"] for e in search(svc, PLATFORM, "e2")["employees"]] == ["E2"]  # by code


def test_client_admin_only_own_client(svc):
    r = search(svc, ACME, "ravi")
    assert [e["code"] for e in r["employees"]] == ["E1"] and r["clients"] == []
    assert search(svc, ACME, "bharat")["clients"] == []


def test_wildcards_are_literal_and_short_queries(svc):
    assert [e["code"] for e in search(svc, PLATFORM, "a_r")["employees"]] == ["E2"]
    assert search(svc, PLATFORM, "_")["employees"] == []  # too short
    assert [e["code"] for e in search(svc, PLATFORM, "0%")["employees"]] == ["B2"]
    assert search(svc, PLATFORM, "a%z")["employees"] == []


def test_employees_cannot_search(svc):
    with pytest.raises(AccessDenied):
        search(svc, User("e", "e@x.in", "E", Role.EMPLOYEE, "h", client_id="acme", employee_code="E1"), "ra")

"""Logins, sign-up, approval and role checks (service level; API tests run in CI)."""
from datetime import date, datetime, timezone

import pytest

from app import auth
from app.domain import Client, EmployeeRecord, Role, UserStatus
from app.engine import Employee, SalaryStructure
from app.services import AccessDenied, AuthService, PayrollService, ServiceError


def setup(repo):
    svc = PayrollService(repo, clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.ensure_rules_seeded()
    return svc, AuthService(svc)


def test_password_hash_and_token():
    stored = auth.hash_password("Secret123")
    assert stored.startswith("scrypt$") and "Secret123" not in stored
    assert auth.verify_password("Secret123", stored) and not auth.verify_password("secret123", stored)
    token = auth.make_token("u1")
    assert auth.read_token(token) == "u1"
    assert auth.read_token(token[:-2] + "xx") is None
    assert auth.read_token(auth.make_token("u1", ttl=-1)) is None
    assert auth.password_problem("short1") == "Use at least 8 characters"
    assert auth.password_problem("longpassword") == "Use letters and at least one number"


def test_client_signup_and_login(repo):
    svc, a = setup(repo)
    user = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "Asha@Acme.in", "Payroll123")
    assert user.role == Role.ADMIN and user.client_id == "acme" and user.email == "asha@acme.in"
    logged_in, token = a.login("ASHA@acme.in", "Payroll123")
    assert a.user_from_token(token).id == logged_in.id
    with pytest.raises(ServiceError, match="incorrect"):
        a.login("asha@acme.in", "wrong")
    with pytest.raises(ServiceError, match="incorrect"):
        a.login("nobody@acme.in", "Payroll123")
    with pytest.raises(ServiceError) as exc:
        a.signup_client(Client(id="acme2", legal_name="X", state="TG"), "", "asha@acme.in", "weak")
    assert set(exc.value.errors) == {"email", "name", "password"}


def test_employee_signup_needs_approval_and_sees_only_self(repo):
    svc, a = setup(repo)
    admin = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    for code in ("E1", "E2"):
        svc.add_employee(EmployeeRecord("acme", Employee(code=code, name=code),
                                        SalaryStructure({"basic": 20000}), date(2026, 4, 1)), admin.email)
    with pytest.raises(ServiceError) as exc:
        a.signup_employee("acme", "E9", "Ravi", "ravi@x.in", "Ravi12345")
    assert exc.value.field == "employee_code"
    emp = a.signup_employee("acme", "E1", "Ravi", "ravi@x.in", "Ravi12345")
    assert emp.status == UserStatus.PENDING
    with pytest.raises(ServiceError, match="waiting for approval"):
        a.login("ravi@x.in", "Ravi12345")
    with pytest.raises(ServiceError, match="already has an account"):
        a.signup_employee("acme", "E1", "Fake", "fake@x.in", "Fake12345")

    a.set_status(admin, emp.id, UserStatus.ACTIVE)
    emp, _ = a.login("ravi@x.in", "Ravi12345")

    run = svc.create_draft("acme", date(2026, 10, 1), user=admin.email)
    assert a.my_payslips(emp) == []  # drafts are never shown
    svc.approve(run.id, "reviewer@acme.in")
    svc.lock(run.id, "reviewer@acme.in")
    slips = a.my_payslips(emp)
    assert [s.employee_code for _, _, s in slips] == ["E1"]  # never E2

    a.update_my_tax(emp, regime="old", age_group="below_60", metro_city=False,
                    parents_senior=False, declarations={"sec_80c": 50000})
    assert repo.get_employee("acme", "E1").employee.tax_regime == "old"
    with pytest.raises(AccessDenied):
        a.list_users(emp)
    with pytest.raises(AccessDenied):
        a.my_payslips(admin)


def test_client_admin_is_limited_to_own_client(repo):
    svc, a = setup(repo)
    platform = a.create_platform_admin("ops@clearpay4u.in", "Platform123")
    acme = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    beta = a.signup_client(Client(id="beta", legal_name="Beta", state="TG"), "Bala", "bala@beta.in", "Payroll123")
    a.check_client(acme, "acme")
    with pytest.raises(AccessDenied):
        a.check_client(acme, "beta")
    a.check_client(platform, "beta")
    assert {u.email for u in a.list_users(acme)} == {"asha@acme.in"}
    assert len(a.list_users(platform)) == 3
    with pytest.raises(AccessDenied):
        a.set_status(acme, beta.id, UserStatus.DISABLED)
    with pytest.raises(AccessDenied):
        a.set_status(acme, platform.id, UserStatus.DISABLED)
    a.set_status(platform, beta.id, UserStatus.DISABLED)
    with pytest.raises(ServiceError, match="disabled"):
        a.login("bala@beta.in", "Payroll123")


def test_bootstrap_admin_only_when_no_users(repo):
    svc, a = setup(repo)
    assert a.ensure_bootstrap_admin(None, None) is None
    first = a.ensure_bootstrap_admin("ops@clearpay4u.in", "Platform123")
    assert first.is_platform_admin
    assert a.ensure_bootstrap_admin("other@clearpay4u.in", "Platform123") is None


def test_admin_can_view_as_employee_read_only(repo):
    svc, a = setup(repo)
    asha = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    bala = a.signup_client(Client(id="beta", legal_name="Beta", state="TG"), "Bala", "bala@beta.in", "Payroll123")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                    SalaryStructure({"basic": 20000}), date(2026, 4, 1)), asha.email)
    viewer, token = a.view_as(asha, "acme", "E1")
    assert viewer.role == Role.EMPLOYEE and viewer.employee_code == "E1"
    assert viewer.impersonated_by == "asha@acme.in" and viewer.name == "Ravi"
    assert a.user_from_token(token).employee_code == "E1"
    assert a.my_record(viewer)[1].code == "E1"
    with pytest.raises(AccessDenied, match="Read-only"):
        a.update_my_tax(viewer, regime="old", age_group="below_60", metro_city=False,
                        parents_senior=False, declarations={})
    with pytest.raises(AccessDenied):
        a.view_as(bala, "acme", "E1")  # other client's admin
    with pytest.raises(AccessDenied):
        a.view_as(viewer, "acme", "E1")  # no chaining
    assert repo.audit_log()[-1].action == "user.view_as"
    a.set_status(a.create_platform_admin("ops@cp.in", "Platform123"), asha.id, UserStatus.DISABLED)
    assert a.user_from_token(token) is None  # disabling the admin ends the view


def test_edit_client_and_employee(repo):
    svc, a = setup(repo)
    svc.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops")
    svc.update_client("acme", {"legal_name": "Acme Textiles Pvt Ltd", "pan": "AAACA1234A", "id": "x"}, "ops")
    c = repo.get_client("acme")
    assert (c.id, c.legal_name, c.pan) == ("acme", "Acme Textiles Pvt Ltd", "AAACA1234A")
    with pytest.raises(ServiceError):
        svc.update_client("acme", {"legal_name": " "}, "ops")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                    SalaryStructure({"basic": 20000}), date(2026, 4, 1)), "ops")
    warnings = svc.update_employee("acme", "E1", "ops", name="Ravi Kumar",
                                   components={"basic": 10000, "special_allowance": 15000},
                                   flags={"pt_applicable": False, "unknown": True})
    e = repo.get_employee("acme", "E1")
    assert e.employee.name == "Ravi Kumar" and e.employee.pt_applicable is False
    assert e.structure.components["special_allowance"] == 15000
    assert len(warnings) == 1  # basic below 50%
    assert repo.audit_log()[-1].detail == "changed: name, pt_applicable, salary"


def test_add_admin_users(repo):
    svc, a = setup(repo)
    ops = a.create_platform_admin("ops@cp.in", "Payroll123")
    asha = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    a.signup_client(Client(id="other", legal_name="Other", state="TG"), "O", "o@other.in", "Payroll123")

    p2 = a.create_admin(ops, name="Priya", email="priya@cp.in", password="Payroll123")
    assert p2.is_platform_admin and p2.status == UserStatus.ACTIVE
    ca = a.create_admin(ops, name="Ravi", email="ravi@acme.in", password="Payroll123", client_id="acme")
    assert ca.client_id == "acme" and a.login("ravi@acme.in", "Payroll123")[0].id == ca.id
    with pytest.raises(ServiceError) as exc:
        a.create_admin(ops, name="X", email="x@cp.in", password="Payroll123", client_id="nope")
    assert exc.value.field == "client_id"

    # A client admin adds admins only to their own company, never platform admins.
    own = a.create_admin(asha, name="Kiran", email="kiran@acme.in", password="Payroll123")
    assert own.client_id == "acme" and not own.is_platform_admin
    with pytest.raises(AccessDenied):
        a.create_admin(asha, name="Y", email="y@other.in", password="Payroll123", client_id="other")
    with pytest.raises(ServiceError) as exc:
        a.create_admin(asha, name="", email="kiran@acme.in", password="weak")
    assert set(exc.value.errors) == {"name", "email", "password"}


def test_login_lockout_and_password_change(repo):
    svc, a = setup(repo)
    a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    for _ in range(5):
        with pytest.raises(ServiceError, match="incorrect"):
            a.login("asha@acme.in", "wrong-pass1")
    with pytest.raises(ServiceError, match="Too many failed attempts"):
        a.login("asha@acme.in", "Payroll123")  # even the right password waits
    a._failures.clear()
    user, _ = a.login("asha@acme.in", "Payroll123")

    with pytest.raises(ServiceError) as e:
        a.change_password(user, "nope", "NewPass123")
    assert e.value.field == "current_password"
    with pytest.raises(ServiceError) as e:
        a.change_password(user, "Payroll123", "short")
    assert e.value.field == "new_password"
    a.change_password(user, "Payroll123", "NewPass123")
    assert a.login("asha@acme.in", "NewPass123")[0].id == user.id


def test_admin_password_reset_limits(repo):
    svc, a = setup(repo)
    ops = a.create_platform_admin("ops@cp.in", "Payroll123")
    asha = a.signup_client(Client(id="acme", legal_name="Acme", state="TG"), "Asha", "asha@acme.in", "Payroll123")
    other = a.signup_client(Client(id="other", legal_name="Other", state="TG"), "O", "o@other.in", "Payroll123")
    a.reset_password(ops, asha.id, "Temp12345")
    assert a.login("asha@acme.in", "Temp12345")
    with pytest.raises(AccessDenied):
        a.reset_password(asha, other.id, "Temp12345")
    with pytest.raises(AccessDenied):
        a.reset_password(asha, ops.id, "Temp12345")

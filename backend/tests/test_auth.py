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
    assert [s.employee_code for _, s in slips] == ["E1"]  # never E2

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

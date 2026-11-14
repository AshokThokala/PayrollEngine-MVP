"""Employee invites, invite registration and the joining profile."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.auth import hash_password
from app.domain import Client, EmployeeRecord, ProfileStatus, Role, User
from app.engine import Employee, SalaryStructure
from app.services import AuthService, PayrollService, ServiceError
from app.services.auth_service import AccessDenied
from app.services.employee_onboarding import EmployeeOnboardingService

NOW = [datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)]

GOOD = {"phone": "9876543210", "date_of_birth": "1995-06-15", "address": "1-2-3 Banjara Hills",
        "city": "Hyderabad", "pincode": "500034", "emergency_name": "Lakshmi", "emergency_phone": "9123456780",
        "uan": "100200300400", "bank_name": "HDFC Bank", "ifsc": "hdfc0001234",
        "pan": "abcde1234f", "account_number": "50100012345678"}


@pytest.fixture
def world(repo):
    NOW[0] = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    svc = PayrollService(repo, clock=lambda: NOW[0])
    svc.ensure_rules_seeded()
    svc.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops")
    svc.add_client(Client(id="other", legal_name="Other", state="TG"), "ops")
    for code in ("E1", "E2"):
        svc.add_employee(EmployeeRecord("acme", Employee(code=code, name=f"Ravi {code}"),
                                        SalaryStructure({"basic": 20000}), date(2026, 4, 1)), "ops")
    auth = AuthService(svc)
    admin = User("a1", "asha@acme.in", "Asha", Role.ADMIN, hash_password("x"), client_id="acme")
    outsider = User("a2", "o@other.in", "O", Role.ADMIN, hash_password("x"), client_id="other")
    repo.save_user(admin)
    repo.save_user(outsider)
    return EmployeeOnboardingService(auth), admin, outsider


def test_invite_register_and_reuse(world):
    eo, admin, outsider = world
    with pytest.raises(AccessDenied):
        eo.invite(outsider, "acme", "E1", "ravi@acme.in")
    invite, token, _ = eo.invite(admin, "acme", "E1", "Ravi@Acme.in")
    assert invite.token_hash != token and invite.expires_at == NOW[0] + timedelta(days=7)
    info = eo.lookup(token)
    assert info["employee_name"] == "Ravi E1" and info["email"] == "ravi@acme.in"
    assert eo.status_list(admin, "acme")[0]["stage"] in ("invited", "not_invited")

    user = eo.accept(token, "Ravi Kumar", "Payroll123")
    assert user.status.value == "active" and user.employee_code == "E1"
    with pytest.raises(ServiceError, match="already used"):
        eo.lookup(token)
    stages = {r["employee_code"]: r["stage"] for r in eo.status_list(admin, "acme")}
    assert stages == {"E1": "registered", "E2": "not_invited"}
    with pytest.raises(ServiceError):
        eo.invite(admin, "acme", "E1", "again@acme.in")  # already has a login


def test_new_invite_replaces_old_and_expiry(world):
    eo, admin, _ = world
    _, first, _ = eo.invite(admin, "acme", "E2", "e2@acme.in")
    _, second, _ = eo.invite(admin, "acme", "E2", "e2@acme.in")
    with pytest.raises(ServiceError, match="not valid"):
        eo.lookup(first)
    NOW[0] += timedelta(days=8)
    with pytest.raises(ServiceError, match="expired"):
        eo.accept(second, "X", "Payroll123")
    assert {r["employee_code"]: r["stage"] for r in eo.status_list(admin, "acme")}["E2"] == "invite_expired"


def test_profile_save_submit_verify(world, repo):
    eo, admin, _ = world
    _, token, _ = eo.invite(admin, "acme", "E1", "ravi@acme.in")
    ravi = eo.accept(token, "Ravi", "Payroll123")

    draft = eo.save_my_profile(ravi, {"phone": "98765 43210", "pan": "abcde1234f"})
    assert draft["status"] == "draft" and draft["phone"] == "9876543210" and draft["pan"] == "ABCDE1234F"
    stored = repo.get_profile("acme", "E1")
    assert stored.pan_enc and "ABCDE1234F" not in stored.pan_enc  # encrypted at rest

    with pytest.raises(ServiceError) as e:
        eo.save_my_profile(ravi, {"ifsc": "HDFC1234567"}, submit=True)
    assert e.value.errors["ifsc"].startswith("IFSC") and e.value.errors["bank_name"] == "Needed before you submit"
    assert "pan" not in e.value.errors  # kept from the draft

    done = eo.save_my_profile(ravi, GOOD, submit=True)
    assert done["status"] == "submitted" and done["ifsc"] == "HDFC0001234"
    with pytest.raises(ServiceError):
        eo.save_my_profile(ravi, GOOD)  # locked while with the employer

    with pytest.raises(ServiceError):
        eo.review(admin, "acme", "E1", approve=False, note="")
    back = eo.review(admin, "acme", "E1", approve=False, note="Bank name does not match IFSC")
    assert back["status"] == "returned"
    eo.save_my_profile(ravi, {**GOOD, "bank_name": "HDFC"}, submit=True)
    ok = eo.review(admin, "acme", "E1", approve=True)
    assert ok["status"] == "verified" and ok["verified_by"] == "asha@acme.in"
    assert eo.profile_for_admin(admin, "acme", "E1")["account_number"] == "50100012345678"
    assert repo.get_profile("acme", "E1").status == ProfileStatus.VERIFIED
    assert {r["employee_code"]: r["stage"] for r in eo.status_list(admin, "acme")}["E1"] == "verified"


def test_profile_validation(world):
    eo, admin, _ = world
    _, token, _ = eo.invite(admin, "acme", "E2", "e2@acme.in")
    user = eo.accept(token, "E2", "Payroll123")
    with pytest.raises(ServiceError) as e:
        eo.save_my_profile(user, {"pan": "ABC", "phone": "12345", "date_of_birth": "2020-01-01", "pincode": "0123"})
    assert set(e.value.errors) == {"pan", "phone", "date_of_birth", "pincode"}


def test_emails_for_each_step(world, repo):
    from app.mailer import Outbox
    eo, admin, _ = world
    box = Outbox()
    eo.mailer, eo.base_url = box, "https://app.clearpay4u.com"
    invite, token, delivery = eo.invite(admin, "acme", "E1", "ravi@acme.in")
    assert delivery == {"sent": True, "to": "ravi@acme.in", "error": None}
    mail = box.sent[-1]
    assert mail.to == "ravi@acme.in" and "Acme" in mail.subject
    assert f"https://app.clearpay4u.com/invite/{token}" in mail.text and token in mail.html

    ravi = eo.accept(token, "Ravi Kumar", "Payroll123")
    eo.save_my_profile(ravi, GOOD, submit=True)
    assert box.sent[-1].to == "asha@acme.in" and "submitted" in box.sent[-1].subject
    out = eo.review(admin, "acme", "E1", approve=False, note="Fix the IFSC")
    assert out["email"]["sent"] and box.sent[-1].to == "ravi@acme.in" and "Fix the IFSC" in box.sent[-1].text
    eo.save_my_profile(ravi, GOOD, submit=True)
    eo.review(admin, "acme", "E1", approve=True)
    assert "verified" in box.sent[-1].subject
    assert any(e.action == "email.sent" for e in repo.audit_log())


def test_email_problems_do_not_block(world, repo):
    from app.mailer import Outbox
    eo, admin, _ = world
    _, token, delivery = eo.invite(admin, "acme", "E1", "ravi@acme.in")  # no mailer
    assert delivery["sent"] is False and "not set up" in delivery["error"]
    eo.mailer, eo.base_url = Outbox(fail=True), "https://app"
    _, token, delivery = eo.invite(admin, "acme", "E2", "e2@acme.in")
    assert delivery["sent"] is False and eo.lookup(token)["employee_code"] == "E2"
    assert any(e.action == "email.failed" for e in repo.audit_log())
    eo.mailer, eo.base_url = Outbox(), ""
    assert "APP_URL" in eo.invite(admin, "acme", "E2", "e2@acme.in")[2]["error"]


def test_smtp_mailer_sends(monkeypatch):
    from app.mailer import Email, MailError, SmtpMailer
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["addr"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    m = SmtpMailer({"SMTP_HOST": "smtp.example.com", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
                    "SMTP_FROM": "CP4U <p@x.in>"})
    m.send(Email("a@b.in", "Hi", "text", "<p>html</p>"))
    assert sent["addr"] == ("smtp.example.com", 587) and sent["tls"] and sent["login"] == "u"
    assert sent["msg"]["To"] == "a@b.in" and sent["msg"].is_multipart()
    with pytest.raises(MailError):
        SmtpMailer({}).send(Email("a@b.in", "Hi", "t"))
    plain = SmtpMailer({"SMTP_HOST": "mailpit", "SMTP_PORT": "1025", "SMTP_SECURITY": "none"})
    sent.clear()
    plain.send(Email("a@b.in", "Hi", "t"))
    assert sent["addr"] == ("mailpit", 1025) and "tls" not in sent and "login" not in sent


def test_admin_edits_demographics_and_job(world, repo):
    eo, admin, outsider = world
    out = eo.save_for_admin(admin, "acme", "E1", {
        "gender": "female", "marital_status": "married", "father_or_spouse_name": "Suresh Rao",
        "father_or_spouse_relation": "spouse", "blood_group": "O+", "personal_email": "Priya@Mail.com",
        "department": "Finance", "designation": "Accountant", "employment_type": "permanent",
        "work_email": "priya@acme.in", "pan": "abcde1234f"})
    assert out["designation"] == "Accountant" and out["personal_email"] == "priya@mail.com" and out["pan"] == "ABCDE1234F"
    assert repo.get_profile("acme", "E1").status == ProfileStatus.DRAFT  # status unchanged
    with pytest.raises(ServiceError) as e:
        eo.save_for_admin(admin, "acme", "E1", {"gender": "x", "blood_group": "Z", "work_email": "nope",
                                                "father_or_spouse_relation": ""})
    assert {"gender", "blood_group", "work_email", "father_or_spouse_relation"} <= set(e.value.errors)
    from app.services.auth_service import AccessDenied
    with pytest.raises(AccessDenied):
        eo.save_for_admin(outsider, "acme", "E1", {"designation": "CEO"})

    # The employee can't change employer-only fields, and keeps the employer's values.
    _, token, _ = eo.invite(admin, "acme", "E1", "ravi@acme.in")
    ravi = eo.accept(token, "Ravi", "Payroll123")
    mine = eo.save_my_profile(ravi, {"designation": "CEO", "blood_group": "A+"})
    assert mine["designation"] == "Accountant" and mine["blood_group"] == "A+"

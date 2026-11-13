"""Employee invites, invite registration and the joining (onboarding) profile.

Flow
  1. A client admin invites an employee by email. The app makes a one-time link (valid 7 days) and emails it
     (SMTP, see app/mailer.py). The link is also shown once so it can be copied if email is not set up.
  2. The employee opens the link, sets a name and password, and is logged in straight away.
  3. The employee fills in contact details, statutory IDs and bank details, then submits.
  4. An admin verifies the profile, or returns it with a note for corrections.
Emails: invite (to the employee), submitted (to the client's admins), returned and verified (to the employee).
Email is best effort: a failure never blocks the step, it is reported back and written to the audit log.

PAN and bank account numbers are encrypted at rest; only the token's SHA-256 hash is stored for invites.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import date, timedelta

from .. import auth, crypto
from ..mailer import MailError
from . import emails
from ..domain import EmployeeProfile, Invite, ProfileStatus, Role, User, UserStatus
from .auth_service import AccessDenied, AuthService
from .payroll_service import ServiceError

INVITE_DAYS = 7

PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MOBILE = re.compile(r"^[6-9][0-9]{9}$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT = re.compile(r"^[0-9]{9,18}$")
UAN = re.compile(r"^[0-9]{12}$")
ESI_IP = re.compile(r"^[0-9]{10}$")
PINCODE = re.compile(r"^[1-9][0-9]{5}$")

# Plain (not encrypted) fields and whether they are needed to submit.
DETAIL_FIELDS = {
    "phone": True, "date_of_birth": True, "address": True, "city": True, "pincode": True,
    "emergency_name": True, "emergency_phone": True, "uan": False, "esi_ip": False,
    "bank_name": True, "ifsc": True,
}
SECRET_FIELDS = {"pan": True, "account_number": True}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EmployeeOnboardingService:
    def __init__(self, auth_service: AuthService, mailer=None, base_url: str = ""):
        self.auth = auth_service
        self.payroll = auth_service.payroll
        self.repo = auth_service.repo
        self.mailer = mailer
        self.base_url = base_url.rstrip("/")

    # --- email (best effort) ------------------------------------------------------------------
    def _deliver(self, email, actor_email: str, entity: str) -> dict:
        """Send one email. Returns {'sent': bool, 'to': ..., 'error': ...}; never raises."""
        if self.mailer is None or not getattr(self.mailer, "enabled", False):
            return {"sent": False, "to": email.to, "error": "Email is not set up on this server"}
        if not self.base_url:
            return {"sent": False, "to": email.to, "error": "APP_URL is not set, so links cannot be built"}
        try:
            self.mailer.send(email)
        except MailError as exc:
            self.payroll._audit(actor_email, "email.failed", entity, f"{email.subject} -> {email.to}: {exc}")
            return {"sent": False, "to": email.to, "error": str(exc)}
        self.payroll._audit(actor_email, "email.sent", entity, f"{email.subject} -> {email.to}")
        return {"sent": True, "to": email.to, "error": None}

    def _link(self, path: str = "/") -> str:
        return f"{self.base_url}{path}"

    def _employee_user(self, client_id: str, code: str) -> User | None:
        return next((u for u in self.repo.list_users(client_id)
                     if u.role == Role.EMPLOYEE and u.employee_code == code), None)

    def _now(self):
        return self.payroll.clock()

    # --- invites ---------------------------------------------------------------------------
    def invite(self, actor: User, client_id: str, employee_code: str, email: str) -> tuple[Invite, str, dict]:
        """Make an invite link for one employee and email it. Any earlier open invite for them stops working.
        Returns (invite, token, delivery) where delivery says whether the email went out."""
        self.auth.check_client(actor, client_id)
        record = self.repo.get_employee(client_id, employee_code)
        if record.exited_on:
            raise ServiceError("This employee has left; they cannot be invited", field="employee_code")
        email = email.strip().lower()
        if not auth.EMAIL.match(email):
            raise ServiceError("Enter a valid email address", field="email")
        if any(u.employee_code == employee_code for u in self.repo.list_users(client_id)):
            raise ServiceError("This employee already has a login", field="employee_code")
        owner = self.repo.find_user_by_email(email)
        if owner:
            raise ServiceError("An account with this email already exists", field="email")
        now = self._now()
        for old in self.repo.list_invites(client_id):
            if old.employee_code == employee_code and not old.accepted_at and not old.revoked:
                old.revoked = True
                self.repo.save_invite(old)
        token = secrets.token_urlsafe(32)
        invite = Invite(id=uuid.uuid4().hex, client_id=client_id, employee_code=employee_code, email=email,
                        token_hash=_hash(token), created_by=actor.email, created_at=now,
                        expires_at=now + timedelta(days=INVITE_DAYS))
        self.repo.save_invite(invite)
        entity = f"employee/{client_id}/{employee_code}"
        self.payroll._audit(actor.email, "invite.create", entity, email)
        client = self.repo.get_client(client_id)
        delivery = self._deliver(emails.invite(email, record.employee.name, client.legal_name,
                                               self._link(f"/invite/{token}"), invite.expires_at),
                                 actor.email, entity)
        return invite, token, delivery

    def revoke(self, actor: User, invite_id: str) -> Invite:
        invite = self.repo.get_invite(invite_id)
        self.auth.check_client(actor, invite.client_id)
        if invite.accepted_at:
            raise ServiceError("This invite was already used")
        invite.revoked = True
        self.repo.save_invite(invite)
        self.payroll._audit(actor.email, "invite.revoke", f"employee/{invite.client_id}/{invite.employee_code}")
        return invite

    def _open_invite(self, token: str) -> Invite:
        invite = self.repo.find_invite_by_hash(_hash(token or ""))
        if invite is None or invite.revoked:
            raise ServiceError("This invite link is not valid. Ask your employer for a new one.")
        if invite.accepted_at:
            raise ServiceError("This invite was already used. Log in with your email and password.")
        if invite.expires_at < self._now():
            raise ServiceError("This invite link has expired. Ask your employer for a new one.")
        return invite

    def lookup(self, token: str) -> dict:
        """What the registration page shows before the employee sets a password."""
        invite = self._open_invite(token)
        client = self.repo.get_client(invite.client_id)
        record = self.repo.get_employee(invite.client_id, invite.employee_code)
        return {"client_name": client.legal_name, "employee_name": record.employee.name,
                "employee_code": invite.employee_code, "email": invite.email,
                "expires_at": invite.expires_at}

    def accept(self, token: str, name: str, password: str) -> User:
        """Create the employee's login from the invite. The account is active straight away."""
        invite = self._open_invite(token)
        if any(u.employee_code == invite.employee_code for u in self.repo.list_users(invite.client_id)):
            raise ServiceError("This employee already has a login")
        user = self.auth._new_user(email=invite.email, name=name, password=password, role=Role.EMPLOYEE,
                                   status=UserStatus.ACTIVE, client_id=invite.client_id,
                                   employee_code=invite.employee_code)
        self.repo.save_user(user)
        invite.accepted_at = self._now()
        self.repo.save_invite(invite)
        if self.repo.get_profile(invite.client_id, invite.employee_code) is None:
            self.repo.save_profile(EmployeeProfile(invite.client_id, invite.employee_code))
        self.payroll._audit(user.email, "invite.accept", f"user/{user.id}",
                            f"employee {invite.client_id}/{invite.employee_code}")
        return user

    # --- the employee's profile ------------------------------------------------------------------
    def _profile(self, client_id: str, code: str) -> EmployeeProfile:
        return self.repo.get_profile(client_id, code) or EmployeeProfile(client_id, code)

    @staticmethod
    def _out(p: EmployeeProfile, reveal: bool) -> dict:
        pan, account = crypto.decrypt(p.pan_enc), crypto.decrypt(p.account_enc)
        return {"client_id": p.client_id, "employee_code": p.employee_code, "status": p.status.value,
                **{k: p.details.get(k, "") for k in DETAIL_FIELDS},
                "pan": (pan or "") if reveal else (crypto.mask(pan) or ""),
                "account_number": (account or "") if reveal else (crypto.mask(account) or ""),
                "submitted_at": p.submitted_at, "verified_by": p.verified_by, "verified_at": p.verified_at,
                "note": p.note}

    def my_profile(self, actor: User) -> dict:
        client_id, code = self.auth._own(actor)
        return self._out(self._profile(client_id, code), reveal=True)

    def _validate(self, values: dict, require: bool) -> dict:
        errors = {}
        checks = {"pan": (PAN, "PAN is 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)"),
                  "phone": (MOBILE, "Enter a 10-digit Indian mobile number"),
                  "emergency_phone": (MOBILE, "Enter a 10-digit Indian mobile number"),
                  "ifsc": (IFSC, "IFSC is 11 characters, the 5th is 0 (e.g. HDFC0001234)"),
                  "account_number": (ACCOUNT, "Account number is 9 to 18 digits"),
                  "uan": (UAN, "UAN is 12 digits"),
                  "esi_ip": (ESI_IP, "ESI IP number is 10 digits"),
                  "pincode": (PINCODE, "Enter a 6-digit PIN code")}
        for key, (pattern, message) in checks.items():
            if values.get(key) and not pattern.match(values[key]):
                errors[key] = message
        dob = values.get("date_of_birth")
        if dob:
            try:
                born = date.fromisoformat(dob)
                today = self._now().date()
                age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
                if age < 14 or age > 100:
                    errors["date_of_birth"] = "Check the date of birth (age must be 14 to 100)"
            except ValueError:
                errors["date_of_birth"] = "Enter a date as YYYY-MM-DD"
        if require:
            for key, needed in {**DETAIL_FIELDS, **SECRET_FIELDS}.items():
                if needed and not values.get(key) and key not in errors:
                    errors[key] = "Needed before you submit"
        return errors

    def save_my_profile(self, actor: User, values: dict, submit: bool = False) -> dict:
        """Save the employee's answers; with submit=True every required field must be filled in."""
        if actor.impersonated_by:
            raise AccessDenied("Read-only while viewing as this employee")
        client_id, code = self.auth._own(actor)
        p = self._profile(client_id, code)
        if p.status in (ProfileStatus.SUBMITTED, ProfileStatus.VERIFIED):
            raise ServiceError("Your details are with your employer. Ask them to return the form to change it.")
        clean = {k: str(v or "").strip() for k, v in values.items() if k in DETAIL_FIELDS or k in SECRET_FIELDS}
        for k in ("pan", "ifsc"):
            if k in clean:
                clean[k] = clean[k].upper()
        for k in ("phone", "emergency_phone", "account_number", "uan", "esi_ip"):
            if k in clean:
                clean[k] = re.sub(r"[\s-]", "", clean[k])
        # Keep stored secrets when the form sends them back blank.
        merged = {**{k: p.details.get(k, "") for k in DETAIL_FIELDS},
                  "pan": crypto.decrypt(p.pan_enc) or "", "account_number": crypto.decrypt(p.account_enc) or ""}
        merged.update({k: v for k, v in clean.items() if v or k in DETAIL_FIELDS})
        errors = self._validate(merged, require=submit)
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        p.details = {k: merged.get(k, "") for k in DETAIL_FIELDS}
        p.pan_enc = crypto.encrypt(merged.get("pan"))
        p.account_enc = crypto.encrypt(merged.get("account_number"))
        if submit:
            p.status, p.submitted_at = ProfileStatus.SUBMITTED, self._now()
        self.repo.save_profile(p)
        entity = f"employee/{client_id}/{code}"
        self.payroll._audit(actor.email, "profile.submit" if submit else "profile.save", entity)
        if submit:
            client = self.repo.get_client(client_id)
            name = self.repo.get_employee(client_id, code).employee.name
            for admin in self.repo.list_users(client_id):
                if admin.role == Role.ADMIN and admin.status == UserStatus.ACTIVE:
                    self._deliver(emails.submitted(admin.email, name, code, client.legal_name, self._link()),
                                  actor.email, entity)
        return self._out(p, reveal=True)

    # --- admin ---------------------------------------------------------------------------------
    def profile_for_admin(self, actor: User, client_id: str, code: str) -> dict:
        self.auth.check_client(actor, client_id)
        self.repo.get_employee(client_id, code)
        self.payroll._audit(actor.email, "profile.view", f"employee/{client_id}/{code}")
        return self._out(self._profile(client_id, code), reveal=True)

    def review(self, actor: User, client_id: str, code: str, *, approve: bool, note: str = "") -> dict:
        self.auth.check_client(actor, client_id)
        p = self.repo.get_profile(client_id, code)
        if p is None or p.status != ProfileStatus.SUBMITTED:
            raise ServiceError("Only a submitted profile can be verified or returned")
        if not approve and not note.strip():
            raise ServiceError("Say what needs to change", field="note")
        if approve:
            p.status, p.verified_by, p.verified_at, p.note = ProfileStatus.VERIFIED, actor.email, self._now(), ""
        else:
            p.status, p.note = ProfileStatus.RETURNED, note.strip()
        self.repo.save_profile(p)
        entity = f"employee/{client_id}/{code}"
        self.payroll._audit(actor.email, "profile.verify" if approve else "profile.return", entity, note.strip())
        out = self._out(p, reveal=True)
        user = self._employee_user(client_id, code)
        if user:
            client = self.repo.get_client(client_id)
            email = (emails.verified(user.email, user.name, client.legal_name, self._link()) if approve else
                     emails.returned(user.email, user.name, client.legal_name, p.note, self._link()))
            out["email"] = self._deliver(email, actor.email, entity)
        return out

    def status_list(self, actor: User, client_id: str) -> list[dict]:
        """One row per current employee: where they are in invite → registration → onboarding."""
        self.auth.check_client(actor, client_id)
        now = self._now()
        users = {u.employee_code: u for u in self.repo.list_users(client_id) if u.role == Role.EMPLOYEE}
        invites: dict[str, Invite] = {}
        for i in self.repo.list_invites(client_id):  # newest first; a revoked invite no longer counts
            if not i.revoked:
                invites.setdefault(i.employee_code, i)
        profiles = {p.employee_code: p for p in self.repo.list_profiles(client_id)}
        rows = []
        for record in self.repo.list_employees(client_id):
            if record.exited_on:
                continue
            code = record.code
            user, invite, profile = users.get(code), invites.get(code), profiles.get(code)
            if profile and profile.status != ProfileStatus.DRAFT:
                stage = profile.status.value
            elif user:
                stage = "registered" if user.status == UserStatus.ACTIVE else user.status.value
            elif invite and not invite.accepted_at:
                stage = "invited" if invite.expires_at >= now else "invite_expired"
            else:
                stage = "not_invited"
            rows.append({"employee_code": code, "name": record.employee.name, "stage": stage,
                         "email": user.email if user else (invite.email if invite else ""),
                         "invite_id": invite.id if invite and stage in ("invited", "invite_expired") else None,
                         "invite_expires_at": invite.expires_at if invite and stage == "invited" else None,
                         "submitted_at": profile.submitted_at if profile else None,
                         "note": profile.note if profile else ""})
        order = {"submitted": 0, "returned": 1, "invite_expired": 2, "not_invited": 3, "invited": 4,
                 "registered": 5, "pending": 5, "disabled": 6, "verified": 7}
        return sorted(rows, key=lambda r: (order.get(r["stage"], 9), r["employee_code"]))

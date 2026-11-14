"""Sign-up, login, approvals and what each role may see.

Roles
  admin, no client      platform admin (payroll service team): every client, rules
  admin, with client    client admin: that client only
  employee              one employee: own profile, payslips and tax declarations
"""
from __future__ import annotations

import uuid
from datetime import date

from .. import auth
from ..domain import Client, Role, RunStatus, User, UserStatus
from ..engine.models import Payslip
from .payroll_service import PayrollService, ServiceError

WRONG_LOGIN = "Email or password is incorrect"
MAX_FAILED_LOGINS = 5          # failures allowed within LOCKOUT_SECONDS ...
LOCKOUT_SECONDS = 15 * 60      # ... before logins for that email pause for this long
_DUMMY_HASH = auth.hash_password("timing-equaliser-not-a-real-password-1")


class AccessDenied(PermissionError):
    pass


class AuthService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo
        self._failures: dict[str, list] = {}  # failed logins per email (this process); slows password guessing

    # --- helpers -------------------------------------------------------------------
    def _new_user(self, *, email: str, name: str, password: str, role: Role,
                  status: UserStatus, client_id: str | None = None,
                  employee_code: str | None = None) -> User:
        errors = {}
        email = email.strip().lower()
        if not auth.EMAIL.match(email):
            errors["email"] = "Enter a valid email address"
        elif self.repo.find_user_by_email(email):
            errors["email"] = "An account with this email already exists; log in instead"
        if not name.strip():
            errors["name"] = "This field is required"
        problem = auth.password_problem(password)
        if problem:
            errors["password"] = problem
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        return User(id=uuid.uuid4().hex, email=email, name=name.strip(), role=role,
                    password_hash=auth.hash_password(password), status=status,
                    client_id=client_id, employee_code=employee_code,
                    created_at=self.payroll.clock())

    # --- accounts ----------------------------------------------------------------------
    def create_platform_admin(self, email: str, password: str, name: str = "Platform admin") -> User:
        user = self._new_user(email=email, name=name, password=password, role=Role.ADMIN,
                              status=UserStatus.ACTIVE)
        self.repo.save_user(user)
        self.payroll._audit(user.email, "user.create", f"user/{user.id}", "platform admin")
        return user

    def ensure_bootstrap_admin(self, email: str | None, password: str | None) -> User | None:
        """Create the first platform admin from ADMIN_EMAIL / ADMIN_PASSWORD if there are no users."""
        if not email or not password or self.repo.list_users():
            return None
        try:
            return self.create_platform_admin(email, password)
        except (ServiceError, ValueError):
            return None  # another worker created it at the same moment

    def signup_client(self, client: Client, name: str, email: str, password: str) -> User:
        """A business signs up: creates the client and its first admin login."""
        user = self._new_user(email=email, name=name, password=password, role=Role.ADMIN,
                              status=UserStatus.ACTIVE, client_id=client.id)
        self.payroll.add_client(client, user=user.email)
        self.repo.save_user(user)
        self.payroll._audit(user.email, "user.signup", f"user/{user.id}", f"client admin for {client.id}")
        return user

    def signup_employee(self, client_id: str, employee_code: str, name: str, email: str,
                        password: str) -> User:
        """An employee signs up; the account stays pending until their employer approves it."""
        try:
            self.payroll.repo.get_client(client_id)
        except LookupError:
            raise ServiceError("No client with this ID; check it with your employer", field="client_id") from None
        try:
            record = self.repo.get_employee(client_id, employee_code)
        except LookupError:
            raise ServiceError("No employee with this code at this client", field="employee_code") from None
        if record.exited_on:
            raise ServiceError("This employee has left the client", field="employee_code")
        if any(u.employee_code == employee_code for u in self.repo.list_users(client_id)):
            raise ServiceError("This employee already has an account", field="employee_code")
        user = self._new_user(email=email, name=name, password=password, role=Role.EMPLOYEE,
                              status=UserStatus.PENDING, client_id=client_id,
                              employee_code=employee_code)
        self.repo.save_user(user)
        self.payroll._audit(user.email, "user.signup", f"user/{user.id}",
                            f"employee {client_id}/{employee_code}, pending approval")
        return user

    def _recent_failures(self, key: str) -> list:
        now = self.payroll.clock().timestamp()
        recent = [t for t in self._failures.get(key, []) if now - t < LOCKOUT_SECONDS]
        self._failures[key] = recent
        return recent

    def login(self, email: str, password: str) -> tuple[User, str]:
        key = (email or "").strip().lower()
        recent = self._recent_failures(key)
        if len(recent) >= MAX_FAILED_LOGINS:
            wait = int(LOCKOUT_SECONDS - (self.payroll.clock().timestamp() - recent[0])) // 60 + 1
            raise ServiceError(f"Too many failed attempts. Try again in {wait} minute{'s' if wait != 1 else ''}.")
        user = self.repo.find_user_by_email(key)
        # Check a password even when the email is unknown, so timing doesn't reveal which emails exist.
        ok = auth.verify_password(password or "", user.password_hash if user else _DUMMY_HASH)
        if user is None or not ok:
            recent.append(self.payroll.clock().timestamp())
            self._failures[key] = recent
            if len(recent) >= MAX_FAILED_LOGINS:
                self.payroll._audit(key or "-", "user.login_locked", f"login/{key}", f"{len(recent)} failed attempts")
            raise ServiceError(WRONG_LOGIN)
        self._failures.pop(key, None)
        if user.status == UserStatus.PENDING:
            raise ServiceError("Your account is waiting for approval from your employer")
        if user.status == UserStatus.DISABLED:
            raise ServiceError("This account is disabled; contact your employer")
        self.payroll._audit(user.email, "user.login", f"user/{user.id}")
        return user, auth.make_token(user.id)

    def user_from_token(self, token: str | None) -> User | None:
        data = auth.read_token_data(token) if token else None
        if data is None:
            return None
        try:
            user = self.repo.get_user(data["uid"])
        except LookupError:
            return None
        if user.status != UserStatus.ACTIVE:
            return None
        if "as" in data:  # an admin viewing as an employee: re-check access on every request
            client_id, code = data["as"]
            if not user.can_manage(client_id):
                return None
            try:
                record = self.repo.get_employee(client_id, code)
            except LookupError:
                return None
            return User(id=f"{user.id}:as:{client_id}/{code}", email=user.email, name=record.employee.name,
                        role=Role.EMPLOYEE, password_hash="", status=UserStatus.ACTIVE,
                        client_id=client_id, employee_code=code, impersonated_by=user.email)
        return user

    def view_as(self, actor: User, client_id: str, code: str) -> tuple[User, str]:
        """Let an admin see the employee portal exactly as one employee sees it (read-only)."""
        if actor.role != Role.ADMIN or actor.impersonated_by:
            raise AccessDenied("Admins only")
        self.check_client(actor, client_id)
        record = self.repo.get_employee(client_id, code)
        token = auth.make_token(actor.id, ttl=auth.VIEW_AS_TTL_SECONDS, view_as=(client_id, code))
        self.payroll._audit(actor.email, "user.view_as", f"{client_id}/{code}", record.employee.name)
        return self.user_from_token(token), token

    # --- admin actions --------------------------------------------------------------
    def check_client(self, actor: User, client_id: str) -> None:
        if not actor.can_manage(client_id):
            raise AccessDenied("You don't have access to this client")

    def create_admin(self, actor: User, *, name: str, email: str, password: str,
                     client_id: str | None = None) -> User:
        """Add an admin login. Platform admins add platform admins (no client) or client admins;
        client admins add admins for their own client only. Employees join through invites."""
        if actor.role != Role.ADMIN:
            raise AccessDenied("Admins only")
        client_id = (client_id or "").strip() or None
        if not actor.is_platform_admin:
            if client_id not in (None, actor.client_id):
                raise AccessDenied("You can only add admins for your own company")
            client_id = actor.client_id
        if client_id is not None:
            try:
                self.repo.get_client(client_id)
            except LookupError:
                raise ServiceError("No client with this ID", field="client_id") from None
        user = self._new_user(email=email, name=name, password=password, role=Role.ADMIN,
                              status=UserStatus.ACTIVE, client_id=client_id)
        self.repo.save_user(user)
        self.payroll._audit(actor.email, "user.create", f"user/{user.id}",
                            f"admin for {client_id}" if client_id else "platform admin")
        return user

    def list_users(self, actor: User, client_id: str | None = None) -> list[User]:
        if actor.role != Role.ADMIN:
            raise AccessDenied("Admins only")
        if not actor.is_platform_admin:
            client_id = actor.client_id
        return self.repo.list_users(client_id)

    def set_status(self, actor: User, user_id: str, status: UserStatus) -> User:
        target = self.repo.get_user(user_id)
        if target.id == actor.id:
            raise ServiceError("You can't change your own account status")
        if target.client_id is None and not actor.is_platform_admin:
            raise AccessDenied("Only platform admins can change platform admins")
        if target.client_id is not None:
            self.check_client(actor, target.client_id)
        target.status = status
        self.repo.save_user(target)
        self.payroll._audit(actor.email, f"user.{status.value}", f"user/{target.id}", target.email)
        return target

    def change_password(self, actor: User, current: str, new: str) -> None:
        """A user changes their own password."""
        if actor.impersonated_by:
            raise AccessDenied("Not available while viewing as an employee")
        user = self.repo.get_user(actor.id)
        if not auth.verify_password(current or "", user.password_hash):
            raise ServiceError("Your current password is incorrect", field="current_password")
        problem = auth.password_problem(new or "")
        if problem:
            raise ServiceError(problem, field="new_password")
        if auth.verify_password(new, user.password_hash):
            raise ServiceError("Choose a password different from the current one", field="new_password")
        user.password_hash = auth.hash_password(new)
        self.repo.save_user(user)
        self.payroll._audit(user.email, "user.password", f"user/{user.id}", "changed own password")

    def reset_password(self, actor: User, user_id: str, new: str) -> User:
        """An admin sets a temporary password for a user they manage (e.g. a forgotten password)."""
        target = self.repo.get_user(user_id)
        if actor.role != Role.ADMIN or actor.impersonated_by:
            raise AccessDenied("Admins only")
        if target.id == actor.id:
            raise ServiceError("Use Change password for your own account")
        if target.client_id is None and not actor.is_platform_admin:
            raise AccessDenied("Only platform admins can reset a platform admin's password")
        if target.client_id is not None:
            self.check_client(actor, target.client_id)
        problem = auth.password_problem(new or "")
        if problem:
            raise ServiceError(problem, field="password")
        target.password_hash = auth.hash_password(new)
        self.repo.save_user(target)
        self._failures.pop(target.email, None)
        self.payroll._audit(actor.email, "user.password_reset", f"user/{target.id}", target.email)
        return target

    # --- employee self-service -----------------------------------------------------------
    def _own(self, actor: User) -> tuple[str, str]:
        if actor.role != Role.EMPLOYEE:
            raise AccessDenied("Employees only")
        return actor.client_id, actor.employee_code

    def my_record(self, actor: User):
        client_id, code = self._own(actor)
        return self.repo.get_client(client_id), self.repo.get_employee(client_id, code)

    def my_payslips(self, actor: User) -> list[tuple[str, date, Payslip]]:
        """(run id, period, payslip) from locked runs only, newest first - drafts are never shown."""
        client_id, code = self._own(actor)
        return self.repo.list_employee_payslips(client_id, code, RunStatus.LOCKED)

    def update_my_tax(self, actor: User, **profile):
        client_id, code = self._own(actor)
        if actor.impersonated_by:
            raise AccessDenied("Read-only while viewing as an employee; edit tax details from the Employees page")
        return self.payroll.update_tax_profile(client_id, code, actor.email, **profile)

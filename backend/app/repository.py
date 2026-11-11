"""Storage interface and an in-memory implementation.

The service layer only talks to ``Repository``. A PostgreSQL implementation
will follow; the in-memory one backs the tests and local demos.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from .domain import (AuditEvent, BillingPlan, Client, EmployeeProfile, EmployeeRecord, Filing, Invite, Invoice,
                     PayrollRun, RunStatus, RunSummary, StatutoryRule, User)
from .engine.models import Payslip


class NotFound(LookupError):
    pass


class Repository(Protocol):
    def add_client(self, client: Client) -> None: ...
    def get_client(self, client_id: str) -> Client: ...
    def list_clients(self) -> list[Client]: ...
    def update_client(self, client: Client) -> None: ...

    def save_employee(self, record: EmployeeRecord) -> None: ...
    def get_employee(self, client_id: str, code: str) -> EmployeeRecord: ...
    def list_employees(self, client_id: str) -> list[EmployeeRecord]: ...

    def save_run(self, run: PayrollRun) -> None: ...
    def get_run(self, run_id: str) -> PayrollRun: ...
    def list_runs(self, client_id: str, *, status: RunStatus | None = None,
                  since: date | None = None, before: date | None = None) -> list[PayrollRun]: ...
    def list_run_summaries(self, client_id: str) -> list[RunSummary]: ...
    def list_employee_payslips(self, client_id: str, code: str,
                               status: RunStatus = RunStatus.LOCKED) -> list[tuple[str, date, Payslip]]: ...

    def save_filing(self, filing: Filing) -> None: ...
    def get_filing(self, filing_id: str) -> Filing: ...
    def list_filings(self, client_id: str | None = None) -> list[Filing]: ...

    def append_audit(self, event: AuditEvent) -> None: ...
    def audit_log(self) -> list[AuditEvent]: ...

    def save_rule(self, rule: StatutoryRule) -> None: ...
    def list_rules(self) -> list[StatutoryRule]: ...

    def save_user(self, user: User) -> None: ...
    def save_billing_plan(self, plan: BillingPlan) -> None: ...
    def get_billing_plan(self, client_id: str) -> BillingPlan | None: ...
    def save_invoice(self, invoice: Invoice) -> None: ...
    def get_invoice(self, invoice_id: str) -> Invoice: ...
    def list_invoices(self, client_id: str | None = None) -> list[Invoice]: ...
    def save_invite(self, invite: Invite) -> None: ...
    def get_invite(self, invite_id: str) -> Invite: ...
    def find_invite_by_hash(self, token_hash: str) -> Invite | None: ...
    def list_invites(self, client_id: str) -> list[Invite]: ...
    def save_profile(self, profile: EmployeeProfile) -> None: ...
    def get_profile(self, client_id: str, employee_code: str) -> EmployeeProfile | None: ...
    def list_profiles(self, client_id: str) -> list[EmployeeProfile]: ...
    def search_employees(self, query: str, client_ids: list[str] | None = None,
                         limit: int = 20) -> list[dict]: ...
    def get_user(self, user_id: str) -> User: ...
    def find_user_by_email(self, email: str) -> User | None: ...
    def list_users(self, client_id: str | None = None) -> list[User]: ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}
        self._employees: dict[tuple[str, str], EmployeeRecord] = {}
        self._runs: dict[str, PayrollRun] = {}
        self._filings: dict[str, Filing] = {}
        self._audit: list[AuditEvent] = []
        self._rules: dict[str, StatutoryRule] = {}
        self._users: dict[str, User] = {}
        self._invites: dict[str, Invite] = {}
        self._profiles: dict[tuple[str, str], EmployeeProfile] = {}
        self._plans: dict[str, BillingPlan] = {}
        self._invoices: dict[str, Invoice] = {}

    @staticmethod
    def _get(store: dict, key, what: str):
        try:
            return store[key]
        except KeyError:
            raise NotFound(f"{what} {key!r} not found") from None

    def add_client(self, client: Client) -> None:
        if client.id in self._clients:
            raise ValueError(f"Client {client.id!r} already exists")
        self._clients[client.id] = client

    def get_client(self, client_id: str) -> Client:
        return self._get(self._clients, client_id, "Client")

    def list_clients(self) -> list[Client]:
        return list(self._clients.values())

    def update_client(self, client: Client) -> None:
        self.get_client(client.id)
        self._clients[client.id] = client

    def save_employee(self, record: EmployeeRecord) -> None:
        self._employees[(record.client_id, record.code)] = record

    def get_employee(self, client_id: str, code: str) -> EmployeeRecord:
        return self._get(self._employees, (client_id, code), "Employee")

    def list_employees(self, client_id: str) -> list[EmployeeRecord]:
        return [r for (cid, _), r in self._employees.items() if cid == client_id]

    def save_run(self, run: PayrollRun) -> None:
        self._runs[run.id] = run

    def get_run(self, run_id: str) -> PayrollRun:
        return self._get(self._runs, run_id, "Payroll run")

    def list_runs(self, client_id: str, *, status: RunStatus | None = None,
                  since: date | None = None, before: date | None = None) -> list[PayrollRun]:
        runs = [r for r in self._runs.values() if r.client_id == client_id
                and (status is None or r.status == status)
                and (since is None or r.period >= since)
                and (before is None or r.period < before)]
        return sorted(runs, key=lambda r: r.period)

    def list_run_summaries(self, client_id: str) -> list[RunSummary]:
        return [RunSummary(r.id, r.client_id, r.period, r.status, r.prepared_by, r.approved_by,
                           r.locked_at, len(r.slips), r.total_gross, r.total_net,
                           r.total_employer_cost)
                for r in reversed(self.list_runs(client_id))]

    def list_employee_payslips(self, client_id: str, code: str,
                               status: RunStatus = RunStatus.LOCKED) -> list[tuple[str, date, Payslip]]:
        runs = self.list_runs(client_id, status=status)
        return [(r.id, r.period, r.slips[code]) for r in reversed(runs) if code in r.slips]

    def save_filing(self, filing: Filing) -> None:
        self._filings[filing.id] = filing

    def get_filing(self, filing_id: str) -> Filing:
        return self._get(self._filings, filing_id, "Filing")

    def list_filings(self, client_id: str | None = None) -> list[Filing]:
        items = [f for f in self._filings.values() if client_id in (None, f.client_id)]
        return sorted(items, key=lambda f: (f.due_on, f.client_id, f.kind))

    def append_audit(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def audit_log(self) -> list[AuditEvent]:
        return list(self._audit)

    def save_rule(self, rule: StatutoryRule) -> None:
        self._rules[rule.id] = rule

    def list_rules(self) -> list[StatutoryRule]:
        return sorted(self._rules.values(), key=lambda r: (r.scope, r.category, r.valid_from))

    def save_user(self, user: User) -> None:
        clash = self.find_user_by_email(user.email)
        if clash and clash.id != user.id:
            raise ValueError(f"A login for {user.email} already exists")
        self._users[user.id] = user

    def get_user(self, user_id: str) -> User:
        return self._get(self._users, user_id, "User")

    def find_user_by_email(self, email: str) -> User | None:
        email = email.strip().lower()
        return next((u for u in self._users.values() if u.email == email), None)

    def list_users(self, client_id: str | None = None) -> list[User]:
        users = [u for u in self._users.values() if client_id in (None, u.client_id)]
        return sorted(users, key=lambda u: (u.client_id or "", u.role.value, u.email))

    def search_employees(self, query: str, client_ids: list[str] | None = None,
                         limit: int = 20) -> list[dict]:
        """Employees whose name or code contains the text (any case); current employees first."""
        q = query.strip().lower()
        hits = [r for (cid, _), r in self._employees.items()
                if (client_ids is None or cid in client_ids)
                and (q in r.employee.name.lower() or q in r.code.lower())]
        hits.sort(key=lambda r: (r.exited_on is not None, r.employee.name.lower(), r.client_id, r.code))
        return [{"client_id": r.client_id, "code": r.code, "name": r.employee.name,
                 "exited_on": r.exited_on} for r in hits[:limit]]

    def save_invite(self, invite: Invite) -> None:
        self.get_client(invite.client_id)
        self._invites[invite.id] = invite

    def get_invite(self, invite_id: str) -> Invite:
        return self._get(self._invites, invite_id, "Invite")

    def find_invite_by_hash(self, token_hash: str) -> Invite | None:
        return next((i for i in self._invites.values() if i.token_hash == token_hash), None)

    def list_invites(self, client_id: str) -> list[Invite]:
        return sorted((i for i in self._invites.values() if i.client_id == client_id),
                      key=lambda i: i.created_at, reverse=True)

    def save_profile(self, profile: EmployeeProfile) -> None:
        self.get_client(profile.client_id)
        self._profiles[(profile.client_id, profile.employee_code)] = profile

    def get_profile(self, client_id: str, employee_code: str) -> EmployeeProfile | None:
        return self._profiles.get((client_id, employee_code))

    def list_profiles(self, client_id: str) -> list[EmployeeProfile]:
        return [p for (cid, _), p in sorted(self._profiles.items()) if cid == client_id]

    def save_billing_plan(self, plan: BillingPlan) -> None:
        self.get_client(plan.client_id)
        self._plans[plan.client_id] = plan

    def get_billing_plan(self, client_id: str) -> BillingPlan | None:
        return self._plans.get(client_id)

    def save_invoice(self, invoice: Invoice) -> None:
        if invoice.number and any(i.number == invoice.number and i.id != invoice.id
                                  for i in self._invoices.values()):
            raise ValueError(f"Invoice number {invoice.number} already used")
        self._invoices[invoice.id] = invoice

    def get_invoice(self, invoice_id: str) -> Invoice:
        return self._get(self._invoices, invoice_id, "Invoice")

    def list_invoices(self, client_id: str | None = None) -> list[Invoice]:
        items = [i for i in self._invoices.values() if client_id in (None, i.client_id)]
        return sorted(items, key=lambda i: (i.period, i.client_id), reverse=True)

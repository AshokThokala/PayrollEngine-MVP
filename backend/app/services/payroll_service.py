"""Payroll workflow: employees, monthly runs (draft -> approved -> locked), filings.

Rules enforced here:
- Maker-checker: the person who approves a run cannot be the person who prepared it.
- A locked run can never be recalculated or changed.
- Every change is written to the audit log.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from .. import rule_schemas
from ..domain import (AuditEvent, Client, EmployeeRecord, Filing, FilingStatus, StatutoryRule,
                      PayrollRun, RunStatus)
from ..engine import PayInputs, RuleBook, SalaryStructure, compute_payslip
from ..engine.money import D
from ..engine.payroll import month_end
from ..engine.wages import check_structure
from ..repository import Repository
from .compliance import filings_for_run

VARIANCE_THRESHOLD = Decimal("0.10")


class ServiceError(ValueError):
    """A request the business rules reject. ``field`` names the input at fault, if any."""

    def __init__(self, message: str, field: str | None = None,
                 errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field = field
        self.errors = errors or {}  # several fields at once: {field: message}


@dataclass
class MonthInput:
    paid_days: Decimal | None = None  # None = work it out from joining/exit dates
    overtime: Decimal = Decimal(0)
    other_earnings: dict[str, Decimal] = field(default_factory=dict)
    other_deductions: dict[str, Decimal] = field(default_factory=dict)


def fy_month_index(d: date) -> int:
    return (d.month - 4) % 12 + 1


def fy_start(d: date) -> date:
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


class PayrollService:
    def __init__(self, repo: Repository, rules: RuleBook | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        """``rules``: a fixed rule book (tests); by default rules are read from the repository."""
        self.repo = repo
        self._fixed_rules = rules
        self.clock = clock

    @property
    def rules(self) -> RuleBook:
        if self._fixed_rules is not None:
            return self._fixed_rules
        return RuleBook.from_records(self.repo.list_rules())

    # --- compliance rules ------------------------------------------------------
    def ensure_rules_seeded(self, user: str = "system") -> int:
        """Load the default rules (app/rules/*.json) into an empty rules table."""
        if self.repo.list_rules():
            return 0
        count = 0
        for scope, category, vf, vt, params, source in RuleBook.load().default_records():
            self.repo.save_rule(StatutoryRule(scope, category, vf, params, vt, source,
                                              created_by=user, created_at=self.clock()))
            count += 1
        self._audit(user, "rules.seed", "statutory_rules", f"{count} default rules")
        return count

    def add_rule(self, scope: str, category: str, valid_from: date, params: dict,
                 source: str, user: str) -> tuple[StatutoryRule, StatutoryRule | None]:
        """Add a new dated version. The previous open version is closed the day before.

        Returns (new rule, previous rule that was closed or None).
        """
        cleaned, errors = rule_schemas.validate(category, scope, params)
        if not source.strip():
            errors["source"] = "Enter the notification, circular or act this comes from"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        versions = [r for r in self.repo.list_rules() if r.scope == scope and r.category == category]
        later = [r for r in versions if r.valid_from >= valid_from]
        if later:
            raise ServiceError(
                f"A version starting {later[0].valid_from} already exists; "
                f"choose a date after {max(r.valid_from for r in versions)}", field="valid_from")
        previous = max(versions, key=lambda r: r.valid_from) if versions else None
        if previous and (previous.valid_to is None or previous.valid_to >= valid_from):
            previous.valid_to = valid_from - timedelta(days=1)
            self.repo.save_rule(previous)
        else:
            previous = None
        rule = StatutoryRule(scope, category, valid_from, cleaned, None, source.strip(),
                             created_by=user, created_at=self.clock())
        self.repo.save_rule(rule)
        self._audit(user, "rule.create", rule.id,
                    f"closed {previous.id} on {previous.valid_to}" if previous else "first version")
        return rule, previous

    # --- audit ---------------------------------------------------------------
    def _audit(self, user: str, action: str, entity: str, detail: str = "") -> None:
        self.repo.append_audit(AuditEvent(self.clock(), user, action, entity, detail))

    # --- clients and employees ----------------------------------------------
    def add_client(self, client: Client, user: str) -> Client:
        try:
            self.repo.get_client(client.id)
        except LookupError:
            pass
        else:
            raise ServiceError(f"A client with ID '{client.id}' already exists", field="id")
        if client.state not in self.rules.supported_states:
            raise ServiceError(f"No compliance rules for {client.state} yet; add its rules on the Compliance rules page first", field="state")
        self.repo.add_client(client)
        self._audit(user, "client.create", client.id)
        return client

    def add_employee(self, record: EmployeeRecord, user: str) -> list[str]:
        client = self.repo.get_client(record.client_id)
        try:
            self.repo.get_employee(record.client_id, record.code)
        except LookupError:
            pass
        else:
            raise ServiceError(f"Employee code '{record.code}' is already used in this client", field="code")
        record.employee.state = client.state
        self.repo.save_employee(record)
        self._audit(user, "employee.create", f"{record.client_id}/{record.code}")
        return self.structure_warnings(record.structure, record.joined_on)

    def structure_warnings(self, structure: SalaryStructure, on: date) -> list[str]:
        return check_structure(structure, self.rules.central("wage_code", on))

    def update_salary(self, client_id: str, code: str, structure: SalaryStructure,
                      user: str) -> list[str]:
        record = self.repo.get_employee(client_id, code)
        old = record.structure.components
        record.structure = structure
        self.repo.save_employee(record)
        self._audit(user, "employee.salary", f"{client_id}/{code}",
                    f"{_fmt(old)} -> {_fmt(structure.components)}")
        return self.structure_warnings(structure, self.clock().date())

    def exit_employee(self, client_id: str, code: str, exit_on: date, user: str) -> None:
        record = self.repo.get_employee(client_id, code)
        if exit_on < record.joined_on:
            raise ServiceError(f"Must be on or after the joining date ({record.joined_on})", field="exit_on")
        record.exited_on = exit_on
        self.repo.save_employee(record)
        self._audit(user, "employee.exit", f"{client_id}/{code}", exit_on.isoformat())

    # --- payroll runs --------------------------------------------------------
    def create_draft(self, client_id: str, period: date, user: str,
                     inputs: dict[str, MonthInput] | None = None) -> PayrollRun:
        client = self.repo.get_client(client_id)
        end = month_end(period)
        run_id = f"{client_id}:{end:%Y-%m}"
        existing = self._find_run(run_id)
        if existing and existing.status != RunStatus.DRAFT:
            raise ServiceError(f"The {end:%Y-%m} run is already {existing.status.value}; it cannot be recalculated", field="period")

        inputs = inputs or {}
        active = [r for r in self.repo.list_employees(client.id) if r.active_in(end)]
        unknown = set(inputs) - {r.code for r in active}
        if unknown:
            raise ServiceError(f"Unknown or inactive employees: {', '.join(sorted(unknown))}", field="inputs")

        rules = self.rules  # read once for the whole run
        days = calendar.monthrange(end.year, end.month)[1]
        ytd = self._ytd(client_id, end)
        previous = self._previous_locked(client_id, end)
        run = PayrollRun(run_id, client_id, end, RunStatus.DRAFT, prepared_by=user)

        for record in sorted(active, key=lambda r: r.code):
            mi = inputs.get(record.code, MonthInput())
            paid = D(mi.paid_days) if mi.paid_days is not None else _default_paid_days(record, end)
            gross_ytd, tds_ytd = ytd.get(record.code, (Decimal(0), Decimal(0)))
            slip = compute_payslip(
                record.employee, record.structure,
                PayInputs(period=end, days_in_month=days, paid_days=paid,
                          overtime=mi.overtime, other_earnings=mi.other_earnings,
                          other_deductions=mi.other_deductions,
                          fy_month_index=fy_month_index(end),
                          ytd_taxable_gross=gross_ytd, ytd_tds=tds_ytd),
                rules,
            )
            run.slips[record.code] = slip
            run.flags += [f"{record.code}: {w}" for w in slip.warnings]
            run.flags += _variance_flags(record.code, slip.net_pay, previous)

        self.repo.save_run(run)
        self._audit(user, "run.draft", run_id, f"{len(run.slips)} employees, net {run.total_net}")
        return run

    def approve(self, run_id: str, user: str) -> PayrollRun:
        run = self.repo.get_run(run_id)
        if run.status != RunStatus.DRAFT:
            raise ServiceError(f"Only a draft can be approved (run is {run.status.value})")
        if user == run.prepared_by:
            raise ServiceError("Maker-checker: the preparer cannot approve their own run")
        run.status, run.approved_by = RunStatus.APPROVED, user
        self.repo.save_run(run)
        self._audit(user, "run.approve", run_id)
        return run

    def lock(self, run_id: str, user: str) -> list[Filing]:
        run = self.repo.get_run(run_id)
        if run.status != RunStatus.APPROVED:
            raise ServiceError(f"Only an approved run can be locked (run is {run.status.value})")
        run.status, run.locked_at = RunStatus.LOCKED, self.clock()
        self.repo.save_run(run)
        client = self.repo.get_client(run.client_id)
        filings = filings_for_run(run, client.state, self.rules)
        for f in filings:
            self.repo.save_filing(f)
        self._audit(user, "run.lock", run_id, f"{len(filings)} filings scheduled")
        return filings

    # --- filings ---------------------------------------------------------------
    def update_filing(self, filing_id: str, status: FilingStatus, user: str,
                      challan_ref: str | None = None) -> Filing:
        filing = self.repo.get_filing(filing_id)
        if status != FilingStatus.PENDING and filing.kind != "form_24q" and not challan_ref:
            raise ServiceError("Enter the challan or acknowledgement reference", field="challan_ref")
        filing.status, filing.challan_ref = status, challan_ref or filing.challan_ref
        self.repo.save_filing(filing)
        self._audit(user, "filing.update", filing_id, f"{status.value} {challan_ref or ''}".strip())
        return filing

    # --- helpers -----------------------------------------------------------------
    def _find_run(self, run_id: str) -> PayrollRun | None:
        try:
            return self.repo.get_run(run_id)
        except LookupError:
            return None

    def _locked_runs(self, client_id: str) -> list[PayrollRun]:
        return [r for r in self.repo.list_runs(client_id) if r.status == RunStatus.LOCKED]

    def _previous_locked(self, client_id: str, end: date) -> PayrollRun | None:
        earlier = [r for r in self._locked_runs(client_id) if r.period < end]
        return earlier[-1] if earlier else None

    def _ytd(self, client_id: str, end: date) -> dict[str, tuple[Decimal, Decimal]]:
        start = fy_start(end)
        totals: dict[str, tuple[Decimal, Decimal]] = {}
        for run in self._locked_runs(client_id):
            if start <= run.period < end:
                for code, slip in run.slips.items():
                    g, t = totals.get(code, (Decimal(0), Decimal(0)))
                    totals[code] = (g + slip.gross, t + slip.amount("tds"))
        return totals


def _default_paid_days(record: EmployeeRecord, end: date) -> Decimal:
    start = max(end.replace(day=1), record.joined_on)
    stop = min(end, record.exited_on) if record.exited_on else end
    return Decimal((stop - start).days + 1)


def _variance_flags(code: str, net: Decimal, previous: PayrollRun | None) -> list[str]:
    if previous is None:
        return []
    old = previous.slips.get(code)
    if old is None:
        return [f"{code}: new in this run"]
    if old.net_pay and abs(net - old.net_pay) / old.net_pay > VARIANCE_THRESHOLD:
        return [f"{code}: net pay changed from {old.net_pay} to {net}"]
    return []


def _fmt(components: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(components.items()))

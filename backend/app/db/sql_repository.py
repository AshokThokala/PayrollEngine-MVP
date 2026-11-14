"""Repository backed by a SQL database (PostgreSQL in production, SQLite in tests).

Each method opens its own connection and runs in one transaction, so the
repository is safe to share between API requests.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

from ..domain import (AuditEvent, BillingPlan, Client, ClientDeduction, ClientLocation, ClientPayCode, Timesheet, TimesheetStatus, PayCode, PayCodeKind,
                      PayCodeTax, DeductionCalc, DeductionCategory, DeductionType,
                      EmployeeDeduction, EmployeeProfile, EmployeeRecord, Filing, FilingStatus,
                      Invite, Invoice, InvoiceStatus, PayrollRun, ProfileStatus, Role, RunStatus, RunSummary, StatutoryRule, User,
                      UserStatus)
from ..engine.models import Employee, Line, Payslip, SalaryStructure
from ..repository import NotFound
from .connection import Database

KINDS = (("earning", "earnings"), ("deduction", "deductions"),
         ("employer", "employer_contributions"))

EMPLOYEE_FLAGS = ("pf_member", "eps_member", "pf_on_full_wages", "esi_covered",
                  "pt_applicable", "lwf_applicable")


def _dec(v) -> Decimal | None:
    return None if v is None else (v if isinstance(v, Decimal) else Decimal(str(v)))


def _date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _dt(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def _bool(v) -> bool | None:
    return None if v is None else bool(v)


class SqlRepository:
    def __init__(self, db: Database):
        self.db = db
        self._ph = "%s" if db.dialect == "postgres" else "?"

    # --- plumbing -------------------------------------------------------------
    def _adapt(self, value: Any) -> Any:
        if self.db.dialect == "postgres":
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @contextmanager
    def _tx(self) -> Iterator["_Cursor"]:
        with self.db.session() as conn:
            try:
                yield _Cursor(conn.cursor(), self)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # --- clients ------------------------------------------------------------------
    def add_client(self, client: Client) -> None:
        with self._tx() as c:
            if c.one("SELECT 1 FROM clients WHERE id = ?", client.id):
                raise ValueError(f"Client {client.id!r} already exists")
            c.run("INSERT INTO clients (id, legal_name, state, pan, tan, pf_code, esi_code,"
                  " pt_registration) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  client.id, client.legal_name, client.state, client.pan, client.tan,
                  client.pf_code, client.esi_code, client.pt_registration)

    def get_client(self, client_id: str) -> Client:
        with self._tx() as c:
            row = c.one("SELECT id, legal_name, state, pan, tan, pf_code, esi_code,"
                        " pt_registration FROM clients WHERE id = ?", client_id)
        if not row:
            raise NotFound(f"Client {client_id!r} not found")
        return Client(*row)

    def update_client(self, client: Client) -> None:
        with self._tx() as c:
            if not c.one("SELECT 1 FROM clients WHERE id = ?", client.id):
                raise NotFound(f"Client {client.id!r} not found")
            c.run("UPDATE clients SET legal_name = ?, state = ?, pan = ?, tan = ?, pf_code = ?,"
                  " esi_code = ?, pt_registration = ? WHERE id = ?",
                  client.legal_name, client.state, client.pan, client.tan, client.pf_code,
                  client.esi_code, client.pt_registration, client.id)

    def list_clients(self) -> list[Client]:
        with self._tx() as c:
            rows = c.all("SELECT id, legal_name, state, pan, tan, pf_code, esi_code,"
                         " pt_registration FROM clients ORDER BY id")
        return [Client(*r) for r in rows]

    # --- employees ------------------------------------------------------------------
    def save_employee(self, record: EmployeeRecord) -> None:
        e = record.employee
        with self._tx() as c:
            exists = c.one("SELECT 1 FROM employees WHERE client_id = ? AND code = ?",
                           record.client_id, e.code)
            values = (e.name, e.state, *(getattr(e, f) for f in EMPLOYEE_FLAGS),
                      e.tax_regime, record.joined_on, record.exited_on, e.tax_age_group,
                      e.metro_city, e.parents_senior, json.dumps(e.tax_declarations, default=str),
                      e.pay_type, e.hourly_rate, e.location_id)
            if exists:
                c.run("UPDATE employees SET name = ?, state = ?, pf_member = ?, eps_member = ?,"
                      " pf_on_full_wages = ?, esi_covered = ?, pt_applicable = ?,"
                      " lwf_applicable = ?, tax_regime = ?, joined_on = ?, exited_on = ?,"
                      " tax_age_group = ?, metro_city = ?, parents_senior = ?, tax_declarations = ?,"
                      " pay_type = ?, hourly_rate = ?, location_id = ? WHERE client_id = ? AND code = ?", *values, record.client_id, e.code)
            else:
                c.run("INSERT INTO employees (name, state, pf_member, eps_member,"
                      " pf_on_full_wages, esi_covered, pt_applicable, lwf_applicable,"
                      " tax_regime, joined_on, exited_on, tax_age_group, metro_city, parents_senior,"
                      " tax_declarations, pay_type, hourly_rate, location_id, client_id, code)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      *values, record.client_id, e.code)
            version, current = self._salary(c, record.client_id, e.code)
            if current != record.structure.components:
                for comp, amount in record.structure.components.items():
                    c.run("INSERT INTO salary_components (client_id, employee_code, version,"
                          " component, amount) VALUES (?, ?, ?, ?, ?)",
                          record.client_id, e.code, version + 1, comp, amount)

    @staticmethod
    def _salary(c: "_Cursor", client_id: str, code: str) -> tuple[int, dict[str, Decimal]]:
        row = c.one("SELECT MAX(version) FROM salary_components"
                    " WHERE client_id = ? AND employee_code = ?", client_id, code)
        version = row[0] if row and row[0] is not None else 0
        rows = c.all("SELECT component, amount FROM salary_components WHERE client_id = ?"
                     " AND employee_code = ? AND version = ? ORDER BY component",
                     client_id, code, version)
        return version, {k: _dec(v) for k, v in rows}

    def _employee_from_row(self, c: "_Cursor", row) -> EmployeeRecord:
        (client_id, code, name, state, *flags, regime, joined, exited,
         age_group, metro, parents_senior, declarations, pay_type, hourly_rate, location_id) = row
        flag_values = dict(zip(EMPLOYEE_FLAGS, map(_bool, flags)))
        _, components = self._salary(c, client_id, code)
        return EmployeeRecord(
            client_id,
            Employee(code=code, name=name, state=state, tax_regime=regime, **flag_values,
                     tax_age_group=age_group, metro_city=bool(metro),
                     parents_senior=bool(parents_senior),
                     tax_declarations=json.loads(declarations or "{}"),
                     pay_type=pay_type or "salaried", hourly_rate=_dec(hourly_rate or 0), location_id=location_id),
            SalaryStructure(components), _date(joined), _date(exited),
        )

    _EMP_COLS = ("client_id, code, name, state, pf_member, eps_member, pf_on_full_wages,"
                 " esi_covered, pt_applicable, lwf_applicable, tax_regime, joined_on, exited_on,"
                 " tax_age_group, metro_city, parents_senior, tax_declarations, pay_type, hourly_rate, location_id")

    def get_employee(self, client_id: str, code: str) -> EmployeeRecord:
        with self._tx() as c:
            row = c.one(f"SELECT {self._EMP_COLS} FROM employees WHERE client_id = ? AND code = ?",
                        client_id, code)
            if not row:
                raise NotFound(f"Employee {(client_id, code)!r} not found")
            return self._employee_from_row(c, row)

    def list_employees(self, client_id: str) -> list[EmployeeRecord]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._EMP_COLS} FROM employees WHERE client_id = ?"
                         " ORDER BY code", client_id)
            return [self._employee_from_row(c, r) for r in rows]

    def search_employees(self, query: str, client_ids: list[str] | None = None,
                         limit: int = 20) -> list[dict]:
        """Employees whose name or code contains the text (any case); current employees first."""
        if client_ids is not None and not client_ids:
            return []
        like = "%" + query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql = ("SELECT client_id, code, name, exited_on FROM employees"
               " WHERE (LOWER(name) LIKE ? ESCAPE '\\' OR LOWER(code) LIKE ? ESCAPE '\\')")
        args: list = [like, like]
        if client_ids is not None:
            sql += f" AND client_id IN ({', '.join('?' for _ in client_ids)})"
            args += list(client_ids)
        sql += " ORDER BY CASE WHEN exited_on IS NULL THEN 0 ELSE 1 END, LOWER(name), client_id, code LIMIT ?"
        with self._tx() as c:
            rows = c.all(sql, *args, int(limit))
        return [{"client_id": cid, "code": code, "name": name, "exited_on": _date(ex)}
                for cid, code, name, ex in rows]

    # --- payroll runs --------------------------------------------------------------
    def save_run(self, run: PayrollRun) -> None:
        with self._tx() as c:
            for table in ("payslip_lines", "payslip_warnings", "payslips", "run_flags"):
                c.run(f"DELETE FROM {table} WHERE run_id = ?", run.id)
            if c.one("SELECT 1 FROM payroll_runs WHERE id = ?", run.id):
                c.run("UPDATE payroll_runs SET status = ?, prepared_by = ?, approved_by = ?,"
                      " locked_at = ? WHERE id = ?",
                      run.status.value, run.prepared_by, run.approved_by, run.locked_at, run.id)
            else:
                c.run("INSERT INTO payroll_runs (id, client_id, period, status, prepared_by,"
                      " approved_by, locked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      run.id, run.client_id, run.period, run.status.value, run.prepared_by,
                      run.approved_by, run.locked_at)
            for i, flag in enumerate(run.flags):
                c.run("INSERT INTO run_flags (run_id, seq, message) VALUES (?, ?, ?)",
                      run.id, i, flag)
            for code, slip in run.slips.items():
                c.run("INSERT INTO payslips (run_id, employee_code, period, statutory_wages,"
                      " gross, total_deductions, net_pay, employer_cost)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      run.id, code, slip.period, slip.statutory_wages, slip.gross,
                      slip.total_deductions, slip.net_pay, slip.employer_cost)
                for kind, attr in KINDS:
                    for i, line in enumerate(getattr(slip, attr)):
                        c.run("INSERT INTO payslip_lines (run_id, employee_code, kind, seq,"
                              " code, label, amount, rule_version)"
                              " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              run.id, code, kind, i, line.code, line.label, line.amount, line.rule)
                for i, w in enumerate(slip.warnings):
                    c.run("INSERT INTO payslip_warnings (run_id, employee_code, seq, message)"
                          " VALUES (?, ?, ?, ?)", run.id, code, i, w)

    def _load_run(self, c: "_Cursor", row) -> PayrollRun:
        run_id, client_id, period, status, prepared_by, approved_by, locked_at = row
        run = PayrollRun(run_id, client_id, _date(period), RunStatus(status), prepared_by,
                         approved_by=approved_by, locked_at=_dt(locked_at))
        run.flags = [r[0] for r in c.all(
            "SELECT message FROM run_flags WHERE run_id = ? ORDER BY seq", run_id)]
        lines: dict[tuple[str, str], list[Line]] = {}
        for code, kind, lcode, label, amount, rule in c.all(
                "SELECT employee_code, kind, code, label, amount, rule_version FROM payslip_lines"
                " WHERE run_id = ? ORDER BY employee_code, kind, seq", run_id):
            lines.setdefault((code, kind), []).append(Line(lcode, label, _dec(amount), rule))
        warnings: dict[str, list[str]] = {}
        for code, msg in c.all("SELECT employee_code, message FROM payslip_warnings"
                               " WHERE run_id = ? ORDER BY employee_code, seq", run_id):
            warnings.setdefault(code, []).append(msg)
        for code, slip_period, wages in c.all(
                "SELECT employee_code, period, statutory_wages FROM payslips WHERE run_id = ?"
                " ORDER BY employee_code", run_id):
            run.slips[code] = Payslip(
                code, _date(slip_period),
                lines.get((code, "earning"), []), lines.get((code, "deduction"), []),
                lines.get((code, "employer"), []), warnings.get(code, []), _dec(wages))
        return run

    _RUN_COLS = "id, client_id, period, status, prepared_by, approved_by, locked_at"

    def get_run(self, run_id: str) -> PayrollRun:
        with self._tx() as c:
            row = c.one(f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE id = ?", run_id)
            if not row:
                raise NotFound(f"Payroll run {run_id!r} not found")
            return self._load_run(c, row)

    def list_runs(self, client_id: str, *, status: RunStatus | None = None,
                  since: date | None = None, before: date | None = None) -> list[PayrollRun]:
        sql, args = f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE client_id = ?", [client_id]
        if status is not None:
            sql, args = sql + " AND status = ?", args + [status.value]
        if since is not None:
            sql, args = sql + " AND period >= ?", args + [since]
        if before is not None:
            sql, args = sql + " AND period < ?", args + [before]
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY period", *args)
            return [self._load_run(c, r) for r in rows]

    def list_run_summaries(self, client_id: str) -> list[RunSummary]:
        with self._tx() as c:
            rows = c.all(
                "SELECT r.id, r.client_id, r.period, r.status, r.prepared_by, r.approved_by,"
                " r.locked_at, COUNT(p.employee_code), COALESCE(SUM(p.gross), 0),"
                " COALESCE(SUM(p.net_pay), 0), COALESCE(SUM(p.employer_cost), 0)"
                " FROM payroll_runs r LEFT JOIN payslips p ON p.run_id = r.id"
                " WHERE r.client_id = ?"
                " GROUP BY r.id, r.client_id, r.period, r.status, r.prepared_by, r.approved_by, r.locked_at"
                " ORDER BY r.period DESC", client_id)
        return [RunSummary(rid, cid, _date(period), RunStatus(status), prep, appr, _dt(locked),
                           int(n), _dec(g), _dec(net), _dec(cost))
                for rid, cid, period, status, prep, appr, locked, n, g, net, cost in rows]

    def list_employee_payslips(self, client_id: str, code: str,
                               status: RunStatus = RunStatus.LOCKED) -> list[tuple[str, date, Payslip]]:
        runs_of = "SELECT id FROM payroll_runs WHERE client_id = ? AND status = ?"
        with self._tx() as c:
            heads = c.all("SELECT p.run_id, r.period, p.period, p.statutory_wages FROM payslips p"
                          " JOIN payroll_runs r ON r.id = p.run_id"
                          " WHERE r.client_id = ? AND r.status = ? AND p.employee_code = ?"
                          " ORDER BY r.period DESC", client_id, status.value, code)
            lines: dict[tuple[str, str], list[Line]] = {}
            for run_id, kind, lcode, label, amount, rule in c.all(
                    "SELECT run_id, kind, code, label, amount, rule_version FROM payslip_lines"
                    f" WHERE employee_code = ? AND run_id IN ({runs_of}) ORDER BY run_id, kind, seq",
                    code, client_id, status.value):
                lines.setdefault((run_id, kind), []).append(Line(lcode, label, _dec(amount), rule))
            warnings: dict[str, list[str]] = {}
            for run_id, msg in c.all(
                    "SELECT run_id, message FROM payslip_warnings"
                    f" WHERE employee_code = ? AND run_id IN ({runs_of}) ORDER BY run_id, seq",
                    code, client_id, status.value):
                warnings.setdefault(run_id, []).append(msg)
        return [(run_id, _date(run_period),
                 Payslip(code, _date(slip_period), lines.get((run_id, "earning"), []),
                         lines.get((run_id, "deduction"), []), lines.get((run_id, "employer"), []),
                         warnings.get(run_id, []), _dec(wages)))
                for run_id, run_period, slip_period, wages in heads]

    # --- filings ---------------------------------------------------------------------
    _FILING_COLS = "id, client_id, kind, period, due_on, status, amount, challan_ref"

    @staticmethod
    def _filing(row) -> Filing:
        fid, client_id, kind, period, due_on, status, amount, challan = row
        return Filing(fid, client_id, kind, period, _date(due_on), FilingStatus(status),
                      _dec(amount), challan)

    def save_filing(self, filing: Filing) -> None:
        with self._tx() as c:
            c.run("DELETE FROM filings WHERE id = ?", filing.id)
            c.run(f"INSERT INTO filings ({self._FILING_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  filing.id, filing.client_id, filing.kind, filing.period, filing.due_on,
                  filing.status.value, filing.amount, filing.challan_ref)

    def get_filing(self, filing_id: str) -> Filing:
        with self._tx() as c:
            row = c.one(f"SELECT {self._FILING_COLS} FROM filings WHERE id = ?", filing_id)
        if not row:
            raise NotFound(f"Filing {filing_id!r} not found")
        return self._filing(row)

    def list_filings(self, client_id: str | None = None) -> list[Filing]:
        sql = f"SELECT {self._FILING_COLS} FROM filings"
        args: tuple = ()
        if client_id is not None:
            sql, args = sql + " WHERE client_id = ?", (client_id,)
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY due_on, client_id, kind", *args)
        return [self._filing(r) for r in rows]

    # --- audit -----------------------------------------------------------------------
    def append_audit(self, event: AuditEvent) -> None:
        with self._tx() as c:
            c.run("INSERT INTO audit_events (at, user_name, action, entity, detail)"
                  " VALUES (?, ?, ?, ?, ?)",
                  event.at, event.user, event.action, event.entity, event.detail)

    def audit_log(self) -> list[AuditEvent]:
        with self._tx() as c:
            rows = c.all("SELECT at, user_name, action, entity, detail FROM audit_events ORDER BY id")
        return [AuditEvent(_dt(a), u, act, ent, d) for a, u, act, ent, d in rows]


    # --- statutory rules -----------------------------------------------------------
    def save_rule(self, rule: StatutoryRule) -> None:
        with self._tx() as c:
            c.run("DELETE FROM statutory_rules WHERE id = ?", rule.id)
            c.run("INSERT INTO statutory_rules (id, scope, category, valid_from, valid_to, params,"
                  " source, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  rule.id, rule.scope, rule.category, rule.valid_from, rule.valid_to,
                  json.dumps(rule.params, default=str), rule.source, rule.created_by,
                  rule.created_at or datetime.now().astimezone())

    def list_rules(self) -> list[StatutoryRule]:
        with self._tx() as c:
            rows = c.all("SELECT scope, category, valid_from, valid_to, params, source, created_by,"
                         " created_at FROM statutory_rules ORDER BY scope, category, valid_from")
        return [StatutoryRule(scope, category, _date(vf), json.loads(params), _date(vt), source,
                              created_by, _dt(created_at))
                for scope, category, vf, vt, params, source, created_by, created_at in rows]


    # --- users ------------------------------------------------------------------------
    _USER_COLS = ("id, email, name, role, password_hash, status, client_id, employee_code,"
                  " created_at")

    @staticmethod
    def _user(row) -> User:
        uid, email, name, role, pw, status, client_id, code, created_at = row
        return User(uid, email, name, Role(role), pw, UserStatus(status), client_id, code, _dt(created_at))

    def save_user(self, user: User) -> None:
        with self._tx() as c:
            clash = c.one("SELECT id FROM users WHERE email = ?", user.email)
            if clash and clash[0] != user.id:
                raise ValueError(f"A login for {user.email} already exists")
            c.run("DELETE FROM users WHERE id = ?", user.id)
            c.run(f"INSERT INTO users ({self._USER_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  user.id, user.email, user.name, user.role.value, user.password_hash,
                  user.status.value, user.client_id, user.employee_code,
                  user.created_at or datetime.now().astimezone())

    def get_user(self, user_id: str) -> User:
        with self._tx() as c:
            row = c.one(f"SELECT {self._USER_COLS} FROM users WHERE id = ?", user_id)
        if not row:
            raise NotFound(f"User {user_id!r} not found")
        return self._user(row)

    def find_user_by_email(self, email: str) -> User | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._USER_COLS} FROM users WHERE email = ?", email.strip().lower())
        return self._user(row) if row else None

    def list_users(self, client_id: str | None = None) -> list[User]:
        sql = f"SELECT {self._USER_COLS} FROM users"
        args: tuple = ()
        if client_id is not None:
            sql, args = sql + " WHERE client_id = ?", (client_id,)
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY client_id, role, email", *args)
        return [self._user(r) for r in rows]


    # --- billing ------------------------------------------------------------------------
    _PLAN_COLS = ("client_id, plan, rate_per_employee, minimum_fee, onboarding_fee, gst_rate,"
                  " billing_email, starts_on")
    _INV_COLS = ("id, client_id, number, period, status, lines, subtotal, cgst, sgst, igst, total,"
                 " issue_date, due_date, paid_on, payment_ref")

    def save_billing_plan(self, plan: BillingPlan) -> None:
        with self._tx() as c:
            c.run("DELETE FROM billing_plans WHERE client_id = ?", plan.client_id)
            c.run(f"INSERT INTO billing_plans ({self._PLAN_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  plan.client_id, plan.plan, plan.rate_per_employee, plan.minimum_fee,
                  plan.onboarding_fee, plan.gst_rate, plan.billing_email, plan.starts_on)

    # --- deduction master and employee deductions -------------------------------------------
    _DT_COLS = ("code, name, category, calc, payslip_label, default_value, max_amount, tax_section,"
                " description, active, system")
    _ED_COLS = "id, client_id, employee_code, deduction_code, value, start_month, end_month, note, created_by"

    @staticmethod
    def _dtype(row) -> DeductionType:
        code, name, cat, calc, label, dv, mx, sec, desc, active, system = row
        return DeductionType(code, name, DeductionCategory(cat), DeductionCalc(calc), label or "",
                             None if dv is None else _dec(dv), None if mx is None else _dec(mx),
                             sec or "", desc or "", bool(active), bool(system))

    def list_deduction_types(self) -> list[DeductionType]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._DT_COLS} FROM deduction_types")
        order = {"statutory": 0, "voluntary": 1, "recovery": 2}
        return sorted((self._dtype(r) for r in rows), key=lambda t: (order[t.category.value], t.name.lower()))

    def get_deduction_type(self, code: str) -> DeductionType | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._DT_COLS} FROM deduction_types WHERE code = ?", code)
        return self._dtype(row) if row else None

    def save_deduction_type(self, t: DeductionType) -> None:
        with self._tx() as c:
            args = (t.name, t.category.value, t.calc.value, t.payslip_label, t.default_value, t.max_amount,
                    t.tax_section, t.description, t.active, t.system)
            if c.one("SELECT 1 FROM deduction_types WHERE code = ?", t.code):
                c.run("UPDATE deduction_types SET name = ?, category = ?, calc = ?, payslip_label = ?,"
                      " default_value = ?, max_amount = ?, tax_section = ?, description = ?, active = ?,"
                      " system = ? WHERE code = ?", *args, t.code)
            else:
                c.run(f"INSERT INTO deduction_types ({self._DT_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      t.code, *args)

    # --- client locations ----------------------------------------------------------------------
    _LOC_COLS = ("id, client_id, name, state, address, city, pincode, pt_registration, lwf_registration, esi_code,"
                 " se_registration, head_office, active")

    @staticmethod
    def _location(row) -> ClientLocation:
        *head, ho, active = row
        return ClientLocation(*[v or "" for v in head], head_office=bool(ho), active=bool(active))

    def list_locations(self, client_id: str) -> list[ClientLocation]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._LOC_COLS} FROM client_locations WHERE client_id = ?", client_id)
        return sorted((self._location(r) for r in rows), key=lambda l: (not l.head_office, l.name.lower()))

    def get_location(self, location_id: str) -> ClientLocation:
        with self._tx() as c:
            row = c.one(f"SELECT {self._LOC_COLS} FROM client_locations WHERE id = ?", location_id)
        if not row:
            raise NotFound(f"Location {location_id!r} not found")
        return self._location(row)

    def save_location(self, loc: ClientLocation) -> None:
        with self._tx() as c:
            c.run("DELETE FROM client_locations WHERE id = ?", loc.id)
            c.run(f"INSERT INTO client_locations ({self._LOC_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  loc.id, loc.client_id, loc.name, loc.state, loc.address, loc.city, loc.pincode,
                  loc.pt_registration, loc.lwf_registration, loc.esi_code, loc.se_registration,
                  loc.head_office, loc.active)

    # --- time sheets ---------------------------------------------------------------------------
    def list_timesheets(self, client_id: str, month) -> list[Timesheet]:
        with self._tx() as c:
            rows = c.all("SELECT client_id, employee_code, month, days, status, note, updated_by, approved_by"
                         " FROM timesheets WHERE client_id = ? AND month = ? ORDER BY employee_code", client_id, month)
        return [Timesheet(cid, code, _date(m), json.loads(days), TimesheetStatus(st), note or "", by or "", ab)
                for cid, code, m, days, st, note, by, ab in rows]

    def save_timesheet(self, t: Timesheet) -> None:
        with self._tx() as c:
            c.run("DELETE FROM timesheets WHERE client_id = ? AND employee_code = ? AND month = ?",
                  t.client_id, t.employee_code, t.month)
            c.run("INSERT INTO timesheets (client_id, employee_code, month, days, status, note, updated_by,"
                  " approved_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", t.client_id, t.employee_code, t.month,
                  json.dumps(t.days, default=str), t.status.value, t.note, t.updated_by, t.approved_by)

    _PC_COLS = ("code, name, kind, tax, calc, default_value, payslip_label, tax_section, description, core,"
                " active, system")

    @staticmethod
    def _paycode(row) -> PayCode:
        code, name, kind, tax, calc, dv, label, sec, desc, core, active, system = row
        return PayCode(code, name, PayCodeKind(kind), PayCodeTax(tax), calc, None if dv is None else _dec(dv),
                       label or "", sec or "", desc or "", bool(core), bool(active), bool(system))

    def list_pay_codes(self) -> list[PayCode]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._PC_COLS} FROM pay_codes")
        return sorted((self._paycode(r) for r in rows), key=lambda p: (p.kind.value, not p.core, p.name.lower()))

    def get_pay_code(self, code: str) -> PayCode | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._PC_COLS} FROM pay_codes WHERE code = ?", code)
        return self._paycode(row) if row else None

    def save_pay_code(self, p: PayCode) -> None:
        with self._tx() as c:
            args = (p.name, p.kind.value, p.tax.value, p.calc, p.default_value, p.payslip_label, p.tax_section,
                    p.description, p.core, p.active, p.system)
            if c.one("SELECT 1 FROM pay_codes WHERE code = ?", p.code):
                c.run("UPDATE pay_codes SET name = ?, kind = ?, tax = ?, calc = ?, default_value = ?, payslip_label = ?,"
                      " tax_section = ?, description = ?, core = ?, active = ?, system = ? WHERE code = ?",
                      *args, p.code)
            else:
                c.run(f"INSERT INTO pay_codes ({self._PC_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      p.code, *args)

    def list_client_pay_codes(self, client_id: str) -> list[ClientPayCode]:
        with self._tx() as c:
            rows = c.all("SELECT client_id, pay_code, enabled, default_value, payslip_label FROM client_pay_codes"
                         " WHERE client_id = ? ORDER BY pay_code", client_id)
        return [ClientPayCode(cid, code, bool(en), None if dv is None else _dec(dv), label or "")
                for cid, code, en, dv, label in rows]

    def save_client_pay_code(self, cp: ClientPayCode) -> None:
        with self._tx() as c:
            c.run("DELETE FROM client_pay_codes WHERE client_id = ? AND pay_code = ?", cp.client_id, cp.pay_code)
            c.run("INSERT INTO client_pay_codes (client_id, pay_code, enabled, default_value, payslip_label)"
                  " VALUES (?, ?, ?, ?, ?)", cp.client_id, cp.pay_code, cp.enabled, cp.default_value,
                  cp.payslip_label)

    def list_client_deductions(self, client_id: str) -> list[ClientDeduction]:
        with self._tx() as c:
            rows = c.all("SELECT client_id, deduction_code, enabled, default_value, max_amount, payslip_label"
                         " FROM client_deductions WHERE client_id = ? ORDER BY deduction_code", client_id)
        return [ClientDeduction(cid, code, bool(en), None if dv is None else _dec(dv),
                                None if mx is None else _dec(mx), label or "")
                for cid, code, en, dv, mx, label in rows]

    def save_client_deduction(self, cd: ClientDeduction) -> None:
        with self._tx() as c:
            c.run("DELETE FROM client_deductions WHERE client_id = ? AND deduction_code = ?",
                  cd.client_id, cd.deduction_code)
            c.run("INSERT INTO client_deductions (client_id, deduction_code, enabled, default_value, max_amount,"
                  " payslip_label) VALUES (?, ?, ?, ?, ?, ?)", cd.client_id, cd.deduction_code, cd.enabled,
                  cd.default_value, cd.max_amount, cd.payslip_label)

    @staticmethod
    def _ededuct(row) -> EmployeeDeduction:
        iid, cid, emp, code, value, start, end, note, by = row
        return EmployeeDeduction(iid, cid, emp, code, _dec(value), _date(start), _date(end), note or "", by or "")

    def list_employee_deductions(self, client_id: str, employee_code: str | None = None) -> list[EmployeeDeduction]:
        sql = f"SELECT {self._ED_COLS} FROM employee_deductions WHERE client_id = ?"
        args = [client_id]
        if employee_code is not None:
            sql += " AND employee_code = ?"
            args.append(employee_code)
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY employee_code, start_month, id", *args)
        return [self._ededuct(r) for r in rows]

    def get_employee_deduction(self, deduction_id: str) -> EmployeeDeduction:
        with self._tx() as c:
            row = c.one(f"SELECT {self._ED_COLS} FROM employee_deductions WHERE id = ?", deduction_id)
        if not row:
            raise NotFound(f"Deduction {deduction_id!r} not found")
        return self._ededuct(row)

    def save_employee_deduction(self, d: EmployeeDeduction) -> None:
        with self._tx() as c:
            c.run("DELETE FROM employee_deductions WHERE id = ?", d.id)
            c.run(f"INSERT INTO employee_deductions ({self._ED_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  d.id, d.client_id, d.employee_code, d.deduction_code, d.value, d.start_month, d.end_month,
                  d.note, d.created_by)

    def delete_employee_deduction(self, deduction_id: str) -> None:
        with self._tx() as c:
            c.run("DELETE FROM employee_deductions WHERE id = ?", deduction_id)

    # --- invites and onboarding profiles ----------------------------------------------------
    _INVITE_COLS = ("id, client_id, employee_code, email, token_hash, created_by, created_at, expires_at,"
                    " accepted_at, revoked")
    _PROFILE_COLS = ("client_id, employee_code, status, details, pan_enc, account_enc, submitted_at,"
                     " verified_by, verified_at, note")

    @staticmethod
    def _invite(row) -> Invite:
        iid, cid, code, email, th, by, created, expires, accepted, revoked = row
        return Invite(iid, cid, code, email, th, by, _dt(created), _dt(expires), _dt(accepted), bool(revoked))

    def save_invite(self, invite: Invite) -> None:
        with self._tx() as c:
            c.run("DELETE FROM invites WHERE id = ?", invite.id)
            c.run(f"INSERT INTO invites ({self._INVITE_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  invite.id, invite.client_id, invite.employee_code, invite.email, invite.token_hash,
                  invite.created_by, invite.created_at, invite.expires_at, invite.accepted_at, invite.revoked)

    def get_invite(self, invite_id: str) -> Invite:
        with self._tx() as c:
            row = c.one(f"SELECT {self._INVITE_COLS} FROM invites WHERE id = ?", invite_id)
        if not row:
            raise NotFound(f"Invite {invite_id!r} not found")
        return self._invite(row)

    def find_invite_by_hash(self, token_hash: str) -> Invite | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._INVITE_COLS} FROM invites WHERE token_hash = ?", token_hash)
        return self._invite(row) if row else None

    def list_invites(self, client_id: str) -> list[Invite]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._INVITE_COLS} FROM invites WHERE client_id = ? ORDER BY created_at DESC",
                         client_id)
        return [self._invite(r) for r in rows]

    @staticmethod
    def _profile(row) -> EmployeeProfile:
        cid, code, status, details, pan, acct, submitted, vby, vat, note = row
        return EmployeeProfile(cid, code, ProfileStatus(status), json.loads(details), pan, acct,
                               _dt(submitted), vby, _dt(vat), note or "")

    def save_profile(self, p: EmployeeProfile) -> None:
        with self._tx() as c:
            c.run("DELETE FROM employee_profiles WHERE client_id = ? AND employee_code = ?",
                  p.client_id, p.employee_code)
            c.run(f"INSERT INTO employee_profiles ({self._PROFILE_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  p.client_id, p.employee_code, p.status.value, json.dumps(p.details, default=str),
                  p.pan_enc, p.account_enc, p.submitted_at, p.verified_by, p.verified_at, p.note)

    def get_profile(self, client_id: str, employee_code: str) -> EmployeeProfile | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._PROFILE_COLS} FROM employee_profiles"
                        " WHERE client_id = ? AND employee_code = ?", client_id, employee_code)
        return self._profile(row) if row else None

    def list_profiles(self, client_id: str) -> list[EmployeeProfile]:
        with self._tx() as c:
            rows = c.all(f"SELECT {self._PROFILE_COLS} FROM employee_profiles WHERE client_id = ?"
                         " ORDER BY employee_code", client_id)
        return [self._profile(r) for r in rows]

    def get_billing_plan(self, client_id: str) -> BillingPlan | None:
        with self._tx() as c:
            row = c.one(f"SELECT {self._PLAN_COLS} FROM billing_plans WHERE client_id = ?", client_id)
        if not row:
            return None
        cid, plan, rate, minimum, onboarding, gst, email, starts = row
        return BillingPlan(cid, plan, _dec(rate), _dec(minimum), _dec(onboarding), _dec(gst), email, _date(starts))

    @staticmethod
    def _invoice(row) -> Invoice:
        (iid, cid, number, period, status, lines, subtotal, cgst, sgst, igst, total,
         issue_date, due_date, paid_on, ref) = row
        return Invoice(iid, cid, _date(period), InvoiceStatus(status), json.loads(lines), _dec(subtotal),
                       _dec(cgst), _dec(sgst), _dec(igst), _dec(total), number, _date(issue_date),
                       _date(due_date), _date(paid_on), ref)

    def save_invoice(self, invoice: Invoice) -> None:
        with self._tx() as c:
            if invoice.number:
                clash = c.one("SELECT id FROM invoices WHERE number = ?", invoice.number)
                if clash and clash[0] != invoice.id:
                    raise ValueError(f"Invoice number {invoice.number} already used")
            c.run("DELETE FROM invoices WHERE id = ?", invoice.id)
            c.run(f"INSERT INTO invoices ({self._INV_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  invoice.id, invoice.client_id, invoice.number, invoice.period, invoice.status.value,
                  json.dumps(invoice.lines, default=str), invoice.subtotal, invoice.cgst, invoice.sgst,
                  invoice.igst, invoice.total, invoice.issue_date, invoice.due_date, invoice.paid_on,
                  invoice.payment_ref)

    def get_invoice(self, invoice_id: str) -> Invoice:
        with self._tx() as c:
            row = c.one(f"SELECT {self._INV_COLS} FROM invoices WHERE id = ?", invoice_id)
        if not row:
            raise NotFound(f"Invoice {invoice_id!r} not found")
        return self._invoice(row)

    def list_invoices(self, client_id: str | None = None) -> list[Invoice]:
        sql, args = f"SELECT {self._INV_COLS} FROM invoices", ()
        if client_id is not None:
            sql, args = sql + " WHERE client_id = ?", (client_id,)
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY period DESC, client_id DESC", *args)
        return [self._invoice(r) for r in rows]


class _Cursor:
    """Small wrapper: write SQL with '?' placeholders; adapts them per database."""

    def __init__(self, cur, repo: SqlRepository):
        self._cur, self._repo = cur, repo

    def _exec(self, sql: str, args: tuple):
        if self._repo._ph != "?":
            sql = sql.replace("?", self._repo._ph)
        self._cur.execute(sql, tuple(self._repo._adapt(a) for a in args))

    def run(self, sql: str, *args) -> None:
        self._exec(sql, args)

    def one(self, sql: str, *args):
        self._exec(sql, args)
        return self._cur.fetchone()

    def all(self, sql: str, *args) -> list:
        self._exec(sql, args)
        return self._cur.fetchall()

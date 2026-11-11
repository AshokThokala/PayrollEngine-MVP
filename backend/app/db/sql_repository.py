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

from ..domain import (AuditEvent, Client, EmployeeRecord, Filing, FilingStatus,
                      PayrollRun, Role, RunStatus, RunSummary, StatutoryRule, User, UserStatus)
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
                      e.metro_city, e.parents_senior, json.dumps(e.tax_declarations, default=str))
            if exists:
                c.run("UPDATE employees SET name = ?, state = ?, pf_member = ?, eps_member = ?,"
                      " pf_on_full_wages = ?, esi_covered = ?, pt_applicable = ?,"
                      " lwf_applicable = ?, tax_regime = ?, joined_on = ?, exited_on = ?,"
                      " tax_age_group = ?, metro_city = ?, parents_senior = ?, tax_declarations = ?"
                      " WHERE client_id = ? AND code = ?", *values, record.client_id, e.code)
            else:
                c.run("INSERT INTO employees (name, state, pf_member, eps_member,"
                      " pf_on_full_wages, esi_covered, pt_applicable, lwf_applicable,"
                      " tax_regime, joined_on, exited_on, tax_age_group, metro_city, parents_senior,"
                      " tax_declarations, client_id, code)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
         age_group, metro, parents_senior, declarations) = row
        flag_values = dict(zip(EMPLOYEE_FLAGS, map(_bool, flags)))
        _, components = self._salary(c, client_id, code)
        return EmployeeRecord(
            client_id,
            Employee(code=code, name=name, state=state, tax_regime=regime, **flag_values,
                     tax_age_group=age_group, metro_city=bool(metro),
                     parents_senior=bool(parents_senior),
                     tax_declarations=json.loads(declarations or "{}")),
            SalaryStructure(components), _date(joined), _date(exited),
        )

    _EMP_COLS = ("client_id, code, name, state, pf_member, eps_member, pf_on_full_wages,"
                 " esi_covered, pt_applicable, lwf_applicable, tax_regime, joined_on, exited_on,"
                 " tax_age_group, metro_city, parents_senior, tax_declarations")

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

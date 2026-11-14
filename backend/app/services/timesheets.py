"""Time entry for salaried and hourly employees.

Salaried employees: a status per day (present, absent, half day, paid leave, holiday, weekly off) and
overtime hours. Absent days and half of each half day are loss of pay; the rest of the month is paid.
Hourly employees: regular and overtime hours per day; pay = hours x hourly rate.

Overtime is paid at twice the ordinary rate of wages (Code on Wages 2019, s.14; OSH Code). For salaried
employees the ordinary hourly rate is monthly wages (basic + DA + retaining allowance) / 26 days / 8 hours.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from ..domain import DAY_STATUSES, RunStatus, Timesheet, TimesheetStatus, User
from ..engine.money import D, paise
from .payroll_service import PayrollService, ServiceError

OT_MULTIPLIER = Decimal(2)
STD_DAYS, STD_HOURS = Decimal(26), Decimal(8)
MAX_HOURS_A_DAY = Decimal(24)
WAGE_CODES = ("basic", "da", "retaining_allowance")


def month_start(value) -> date:
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:7] + "-01")
    except ValueError:
        raise ServiceError("Choose a month", field="month") from None
    return d.replace(day=1)


def _num(v) -> Decimal:
    if v in (None, ""):
        return Decimal(0)
    return D(v)


def summarize(sheet: Timesheet | None, hourly: bool) -> dict:
    totals = {k: 0 for k in DAY_STATUSES}
    regular = ot = Decimal(0)
    for day in (sheet.days if sheet else {}).values():
        status = day.get("status") or ("P" if hourly else "")
        if status in totals:
            totals[status] += 1
        regular += _num(day.get("hours"))
        ot += _num(day.get("ot"))
    lop = Decimal(totals["A"]) + Decimal(totals["HD"]) / 2
    return {"days": totals, "lop_days": lop, "regular_hours": regular, "ot_hours": ot}


def ordinary_hourly_rate(record) -> Decimal:
    if record.employee.pay_type == "hourly":
        return record.employee.hourly_rate
    comps = record.structure.components
    wages = sum((comps.get(k, Decimal(0)) for k in WAGE_CODES), Decimal(0))
    return wages / STD_DAYS / STD_HOURS


def overtime_pay(record, ot_hours: Decimal) -> Decimal:
    return paise(ordinary_hourly_rate(record) * OT_MULTIPLIER * ot_hours)


class TimeService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo

    def _locked(self, client_id: str, month: date) -> bool:
        run = self.payroll._find_run(f"{client_id}:{month:%Y-%m}")
        return run is not None and run.status != RunStatus.DRAFT

    def month_view(self, client_id: str, month) -> dict:
        m = month_start(month)
        self.repo.get_client(client_id)
        days_in_month = calendar.monthrange(m.year, m.month)[1]
        end = m.replace(day=days_in_month)
        sheets = {t.employee_code: t for t in self.repo.list_timesheets(client_id, m)}
        rows = []
        for r in self.repo.list_employees(client_id):
            if not r.active_in(end):
                continue
            hourly = r.employee.pay_type == "hourly"
            sheet = sheets.get(r.code)
            summary = summarize(sheet, hourly)
            rows.append({
                "code": r.code, "name": r.employee.name, "pay_type": r.employee.pay_type,
                "hourly_rate": r.employee.hourly_rate, "joined_on": r.joined_on, "exited_on": r.exited_on,
                "status": sheet.status.value if sheet else None, "days": sheet.days if sheet else {},
                "note": sheet.note if sheet else "", "approved_by": sheet.approved_by if sheet else None,
                **summary,
                "paid_days": None if hourly else D(days_in_month) - summary["lop_days"],
                "ot_rate": paise(ordinary_hourly_rate(r) * OT_MULTIPLIER),
                "ot_pay": overtime_pay(r, summary["ot_hours"]),
                "hourly_pay": paise(r.employee.hourly_rate * summary["regular_hours"]) if hourly else None,
            })
        return {"month": m, "days_in_month": days_in_month, "locked": self._locked(client_id, m),
                "statuses": DAY_STATUSES, "employees": rows}

    def save(self, actor: User, client_id: str, code: str, month, days: dict, note: str = "",
             approve: bool = False) -> Timesheet:
        m = month_start(month)
        record = self.repo.get_employee(client_id, code)
        if self._locked(client_id, m):
            raise ServiceError(f"The {m:%B %Y} payroll is already approved; its time can no longer change")
        hourly = record.employee.pay_type == "hourly"
        n = calendar.monthrange(m.year, m.month)[1]
        clean: dict[str, dict] = {}
        errors: dict[str, str] = {}
        for key, day in (days or {}).items():
            try:
                d = int(key)
            except ValueError:
                errors["days"] = f"Unknown day {key!r}"
                continue
            if not 1 <= d <= n:
                errors["days"] = f"{m:%B} has {n} days"
                continue
            day = day or {}
            status = (day.get("status") or "").upper()
            if status and status not in DAY_STATUSES:
                errors[f"day_{d}"] = f"Day {d}: unknown status {status!r}"
            try:
                hours, ot = _num(day.get("hours")), _num(day.get("ot"))
            except (InvalidOperation, ValueError, TypeError):
                errors[f"day_{d}"] = f"Day {d}: enter hours as numbers"
                continue
            if hours < 0 or ot < 0:
                errors[f"day_{d}"] = f"Day {d}: hours cannot be negative"
            elif hours + ot > MAX_HOURS_A_DAY:
                errors[f"day_{d}"] = f"Day {d}: more than 24 hours"
            if status in ("A",) and hours > 0:
                errors[f"day_{d}"] = f"Day {d}: absent but has hours"
            entry = {}
            if status:
                entry["status"] = status
            if hours:
                entry["hours"] = str(hours)
            if ot:
                entry["ot"] = str(ot)
            if entry:
                clean[str(d)] = entry
        if errors:
            raise ServiceError("Check the highlighted days", errors=errors)
        sheet = Timesheet(client_id, code, m, clean,
                          TimesheetStatus.APPROVED if approve else TimesheetStatus.DRAFT, note.strip(),
                          actor.email, actor.email if approve else None)
        self.repo.save_timesheet(sheet)
        self.payroll._audit(actor.email, "time.approve" if approve else "time.save", f"employee/{client_id}/{code}",
                            f"{m:%Y-%m}" + (" (hourly)" if hourly else ""))
        return sheet

    def approve(self, actor: User, client_id: str, month, codes: list[str] | None = None,
                approve: bool = True) -> int:
        """Approve (or reopen) saved time sheets for the month. Returns how many changed."""
        m = month_start(month)
        if self._locked(client_id, m):
            raise ServiceError(f"The {m:%B %Y} payroll is already approved")
        changed = 0
        for t in self.repo.list_timesheets(client_id, m):
            if codes and t.employee_code not in codes:
                continue
            target = TimesheetStatus.APPROVED if approve else TimesheetStatus.DRAFT
            if t.status != target:
                t.status, t.approved_by = target, actor.email if approve else None
                self.repo.save_timesheet(t)
                changed += 1
        if changed:
            self.payroll._audit(actor.email, "time.approve" if approve else "time.reopen", f"client/{client_id}",
                                f"{m:%Y-%m}: {changed} sheet(s)")
        return changed

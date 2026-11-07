"""Compliance calendar: which returns and payments fall due for a pay month.

Due-date rules are kept here as simple functions for the MVP.
VERIFY each date with a practising CA before live use.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain import Filing, PayrollRun

QUARTER_END_MONTHS = {6: ("Q1", (7, 31)), 9: ("Q2", (10, 31)), 12: ("Q3", (1, 31)), 3: ("Q4", (5, 31))}

PF_CODES = ("pf_employee", "pf_employer_epf", "pf_employer_eps", "pf_edli", "pf_admin")
ESI_CODES = ("esi_employee", "esi_employer")
LWF_CODES = ("lwf_employee", "lwf_employer")


def _next_month(d: date, day: int) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, day)


def _fy_label(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _sum(run: PayrollRun, codes: tuple[str, ...]) -> Decimal:
    return sum((s.amount(c) for s in run.slips.values() for c in codes), Decimal(0))


def filings_for_run(run: PayrollRun, state: str) -> list[Filing]:
    """Filings created when a payroll run is locked."""
    p = run.period
    month = p.strftime("%Y-%m")
    cid = run.client_id

    def make(kind: str, period: str, due: date, amount: Decimal | None) -> Filing:
        return Filing(id=f"{cid}:{kind}:{period}", client_id=cid, kind=kind,
                      period=period, due_on=due, amount=amount)

    out: list[Filing] = []
    pf = _sum(run, PF_CODES)
    if pf:
        out.append(make("pf", month, _next_month(p, 15), pf))
    esi = _sum(run, ESI_CODES)
    if esi:
        out.append(make("esi", month, _next_month(p, 15), esi))

    tds = _sum(run, ("tds",))
    tds_due = date(p.year, 4, 30) if p.month == 3 else _next_month(p, 7)
    out.append(make("tds_deposit", month, tds_due, tds))

    if state == "TG":
        pt = _sum(run, ("pt",))
        if pt:
            out.append(make("pt", month, _next_month(p, 10), pt))
        lwf = _sum(run, LWF_CODES)
        if lwf:
            out.append(make("lwf", str(p.year), date(p.year + 1, 1, 31), lwf))

    if p.month in QUARTER_END_MONTHS:
        quarter, (m, d) = QUARTER_END_MONTHS[p.month]
        year = p.year + 1 if p.month == 12 else p.year
        out.append(make("form_24q", f"{_fy_label(p)} {quarter}", date(year, m, d), None))
    return out


def overdue(filings: list[Filing], today: date) -> list[Filing]:
    return [f for f in filings if f.status.value == "pending" and f.due_on < today]

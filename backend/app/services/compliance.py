"""Compliance calendar: which returns and payments fall due for a pay month.

Due dates come from the date-effective rules (category ``filing_due_dates`` and the
state's ``professional_tax`` / ``lwf`` rules), so they can be changed on the
Compliance rules page without a code release.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain import Filing, PayrollRun
from ..engine.rules import RuleBook, RuleNotFound

QUARTER_END_MONTHS = {6: "Q1", 9: "Q2", 12: "Q3", 3: "Q4"}

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


def _mmdd(value: str, after: date) -> date:
    """First date matching 'MM-DD' that falls after the given date."""
    month, day = (int(x) for x in value.split("-"))
    candidate = date(after.year, month, day)
    return candidate if candidate > after else date(after.year + 1, month, day)


def filings_for_run(run: PayrollRun, state: str, rules: RuleBook) -> list[Filing]:
    """Filings created when a payroll run is locked."""
    p = run.period
    due = rules.central("filing_due_dates", p)
    month = p.strftime("%Y-%m")
    cid = run.client_id

    def make(kind: str, period: str, due: date, amount: Decimal | None) -> Filing:
        return Filing(id=f"{cid}:{kind}:{period}", client_id=cid, kind=kind,
                      period=period, due_on=due, amount=amount)

    out: list[Filing] = []
    pf = _sum(run, PF_CODES)
    if pf:
        out.append(make("pf", month, _next_month(p, int(due["pf_due_day"])), pf))
    esi = _sum(run, ESI_CODES)
    if esi:
        out.append(make("esi", month, _next_month(p, int(due["esi_due_day"])), esi))

    tds = _sum(run, ("tds",))
    tds_due = _mmdd(due["tds_march_due"], p) if p.month == 3 else _next_month(p, int(due["tds_due_day"]))
    out.append(make("tds_deposit", month, tds_due, tds))

    pt = _sum(run, ("pt",))
    if pt:
        pt_rule = rules.state(state, "professional_tax", p)
        out.append(make("pt", month, _next_month(p, int(pt_rule["due_day"])), pt))
    lwf = _sum(run, LWF_CODES)
    if lwf:
        lwf_rule = rules.state(state, "lwf", p)
        lwf_due = _mmdd(f"{int(lwf_rule['due_month']):02d}-{int(lwf_rule['due_day']):02d}", p)
        out.append(make("lwf", str(p.year), lwf_due, lwf))

    if p.month in QUARTER_END_MONTHS:
        quarter = QUARTER_END_MONTHS[p.month]
        out.append(make("form_24q", f"{_fy_label(p)} {quarter}",
                        _mmdd(due[f"form_24q_{quarter.lower()}_due"], p), None))
    return out


def overdue(filings: list[Filing], today: date) -> list[Filing]:
    return [f for f in filings if f.status.value == "pending" and f.due_on < today]

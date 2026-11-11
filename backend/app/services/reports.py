"""Reports for a client. Each returns {title, subtitle, columns, rows, totals}.

Column types: text, money, number, date, status. Totals are filled for money/number columns
where adding them up makes sense.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from ..domain import FilingStatus, RunStatus
from ..engine.payroll import month_end
from ..repository import Repository
from .compliance import ESI_CODES, LWF_CODES, PF_CODES

ZERO = Decimal(0)

CATALOG = [
    {"key": "salary_register", "title": "Salary register",
     "description": "Every employee's earnings, deductions and net pay for one month.", "params": ["month"]},
    {"key": "statutory_summary", "title": "Statutory dues by month",
     "description": "PF, ESI, Professional Tax, LWF and TDS to pay for each month of a financial year.", "params": ["fy"]},
    {"key": "cost_trend", "title": "Payroll cost trend",
     "description": "Headcount, gross, net and employer cost for the last 12 months.", "params": []},
    {"key": "compliance_status", "title": "Compliance status",
     "description": "Every filing with its due date and status, overdue first.", "params": []},
    {"key": "tax_summary", "title": "Income tax summary",
     "description": "Each employee's regime, year-to-date gross and TDS for a financial year.", "params": ["fy"]},
]


class UnknownReport(LookupError):
    pass


def _col(key, label, type_="text"):
    return {"key": key, "label": label, "type": type_}


def _totals(columns, rows, keys):
    return {c["key"]: sum((Decimal(str(r[c["key"]])) for r in rows), ZERO)
            for c in columns if c["key"] in keys}


def fy_bounds(fy: int) -> tuple[date, date]:
    """FY 2026 = April 2026 to March 2027."""
    return date(fy, 4, 1), date(fy + 1, 3, 31)


def salary_register(repo: Repository, client_id: str, month: date) -> dict:
    end = month_end(month)
    run_id = f"{client_id}:{end:%Y-%m}"
    try:
        run = repo.get_run(run_id)
    except LookupError:
        run = None
    names = {r.code: r.employee.name for r in repo.list_employees(client_id)}
    columns = [_col("code", "Code"), _col("name", "Name"), _col("gross", "Gross", "money"),
               _col("pf", "PF", "money"), _col("esi", "ESI", "money"), _col("pt", "PT", "money"),
               _col("tds", "TDS", "money"), _col("other", "Other deductions", "money"),
               _col("net", "Net pay", "money"), _col("employer_cost", "Employer cost", "money")]
    rows = []
    for code, slip in sorted((run.slips if run else {}).items()):
        statutory = {"pf": slip.amount("pf_employee"), "esi": slip.amount("esi_employee"),
                     "pt": slip.amount("pt"), "tds": slip.amount("tds")}
        other = slip.total_deductions - sum(statutory.values(), ZERO)  # LWF, advances, etc.
        rows.append({"code": code, "name": names.get(code, code), "gross": slip.gross, **statutory,
                     "other": other, "net": slip.net_pay,
                     "employer_cost": slip.employer_cost})
    status = run.status.value if run else "no run"
    return {"title": f"Salary register — {end:%B %Y}",
            "subtitle": f"Run status: {status}" + ("" if not run or run.status == RunStatus.LOCKED else " (not final)"),
            "columns": columns, "rows": rows,
            "totals": _totals(columns, rows, {"gross", "pf", "esi", "pt", "tds", "other", "net", "employer_cost"})}


def statutory_summary(repo: Repository, client_id: str, fy: int) -> dict:
    start, end = fy_bounds(fy)
    runs = repo.list_runs(client_id, status=RunStatus.LOCKED, since=start, before=date(end.year, 4, 1))
    columns = [_col("month", "Month"), _col("pf", "PF (employee + employer)", "money"),
               _col("esi", "ESI (employee + employer)", "money"), _col("pt", "Professional Tax", "money"),
               _col("lwf", "LWF", "money"), _col("tds", "TDS", "money"), _col("total", "Total", "money")]
    rows = []
    for run in runs:
        sums = {"pf": PF_CODES, "esi": ESI_CODES, "pt": ("pt",), "lwf": LWF_CODES, "tds": ("tds",)}
        row = {k: sum((s.amount(c) for s in run.slips.values() for c in codes), ZERO) for k, codes in sums.items()}
        row["total"] = sum(row.values(), ZERO)
        rows.append({"month": f"{run.period:%b %Y}", **row})
    return {"title": f"Statutory dues — FY {fy}-{str(fy + 1)[2:]}", "subtitle": "Locked runs only",
            "columns": columns, "rows": rows,
            "totals": _totals(columns, rows, {"pf", "esi", "pt", "lwf", "tds", "total"})}


def cost_trend(repo: Repository, client_id: str, today: date) -> dict:
    summaries = [s for s in repo.list_run_summaries(client_id)][:12]
    columns = [_col("month", "Month"), _col("status", "Status", "status"), _col("employees", "Employees", "number"),
               _col("gross", "Gross", "money"), _col("net", "Net pay", "money"),
               _col("employer_cost", "Employer cost", "money")]
    rows = [{"month": f"{s.period:%b %Y}", "status": s.status.value, "employees": s.employees,
             "gross": s.total_gross, "net": s.total_net, "employer_cost": s.total_employer_cost}
            for s in reversed(summaries)]
    return {"title": "Payroll cost trend", "subtitle": "Last 12 runs, oldest first",
            "columns": columns, "rows": rows, "chart": {"x": "month", "y": "employer_cost"},
            "totals": _totals(columns, rows, {"gross", "net", "employer_cost"})}


def compliance_status(repo: Repository, client_id: str, today: date) -> dict:
    labels = {"pf": "PF", "esi": "ESI", "tds_deposit": "TDS deposit", "pt": "Professional Tax",
              "lwf": "LWF", "form_24q": "Quarterly TDS return (Form 138)"}
    filings = repo.list_filings(client_id)
    columns = [_col("due_on", "Due", "date"), _col("filing", "Filing"), _col("period", "Period"),
               _col("amount", "Amount", "money"), _col("status", "Status", "status"), _col("reference", "Reference")]

    def state(f):
        if f.status == FilingStatus.PENDING and f.due_on < today:
            return "overdue"
        return f.status.value
    rows = [{"due_on": f.due_on.isoformat(), "filing": labels.get(f.kind, f.kind), "period": f.period,
             "amount": f.amount or ZERO, "status": state(f), "reference": f.challan_ref or ""}
            for f in filings]
    rows.sort(key=lambda r: (r["status"] != "overdue", r["status"] != "pending", r["due_on"]))
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    subtitle = " · ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "No filings yet"
    return {"title": "Compliance status", "subtitle": subtitle, "columns": columns, "rows": rows,
            "totals": _totals(columns, rows, {"amount"})}


def tax_summary(repo: Repository, client_id: str, fy: int) -> dict:
    start, end = fy_bounds(fy)
    runs = repo.list_runs(client_id, status=RunStatus.LOCKED, since=start, before=date(end.year, 4, 1))
    gross, tds, months = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO), defaultdict(int)
    for run in runs:
        for code, slip in run.slips.items():
            gross[code] += slip.gross
            tds[code] += slip.amount("tds")
            months[code] += 1
    columns = [_col("code", "Code"), _col("name", "Name"), _col("regime", "Regime"),
               _col("months", "Months paid", "number"), _col("gross", "Gross YTD", "money"),
               _col("tds", "TDS YTD", "money")]
    rows = [{"code": r.code, "name": r.employee.name,
             "regime": "Old" if r.employee.tax_regime == "old" else "New",
             "months": months[r.code], "gross": gross[r.code], "tds": tds[r.code]}
            for r in sorted(repo.list_employees(client_id), key=lambda r: r.code)
            if months[r.code] or not r.exited_on]
    return {"title": f"Income tax summary — FY {fy}-{str(fy + 1)[2:]}", "subtitle": "Locked runs only",
            "columns": columns, "rows": rows, "totals": _totals(columns, rows, {"gross", "tds"})}


def run_report(repo: Repository, client_id: str, key: str, *, month: date | None, fy: int | None,
               today: date) -> dict:
    default_fy = today.year if today.month >= 4 else today.year - 1
    if key == "salary_register":
        return salary_register(repo, client_id, month or today)
    if key == "statutory_summary":
        return statutory_summary(repo, client_id, fy or default_fy)
    if key == "cost_trend":
        return cost_trend(repo, client_id, today)
    if key == "compliance_status":
        return compliance_status(repo, client_id, today)
    if key == "tax_summary":
        return tax_summary(repo, client_id, fy or default_fy)
    raise UnknownReport(f"Report {key!r} not found")

"""The Tax rules page: income tax rules in force on a date, and a regime comparison calculator."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..engine.money import D
from ..engine.tds import DECLARATION_KEYS, AnnualSalary, explain
from .payroll_service import PayrollService, ServiceError

CATEGORIES = {"new": "income_tax_new_regime", "old": "income_tax_old_regime"}
TDS_DUE_KEYS = ("tds_due_day", "tds_march_due", "form_24q_q1_due", "form_24q_q2_due",
                "form_24q_q3_due", "form_24q_q4_due")


def fy_start(on: date) -> date:
    return date(on.year if on.month >= 4 else on.year - 1, 4, 1)


def tax_year_label(on: date) -> str:
    start = fy_start(on).year
    return f"{start}-{str(start + 1)[2:]}"


def _version(rule) -> dict:
    data = dict(rule.data)
    return {"version": rule.version, "valid_from": data.pop("valid_from"), "valid_to": data.pop("valid_to", None),
            "source": data.pop("source", ""), "params": data}


def overview(svc: PayrollService, on: date) -> dict:
    book = svc.rules
    try:
        regimes = {k: _version(book.central(cat, on)) for k, cat in CATEGORIES.items()}
    except LookupError as exc:
        raise ServiceError(f"No income tax rules for {on.isoformat()}", field="on") from exc
    due = book.central("filing_due_dates", on)
    history = [{"id": r.id, "category": r.category, "regime": "new" if r.category == CATEGORIES["new"] else "old",
                "valid_from": r.valid_from, "valid_to": r.valid_to, "source": r.source,
                "created_by": r.created_by}
               for r in svc.repo.list_rules() if r.category in CATEGORIES.values()]
    history.sort(key=lambda r: (r["valid_from"], r["regime"]), reverse=True)
    return {"on": on, "tax_year": tax_year_label(on), "regimes": regimes,
            "due_dates": {"version": due.version, **{k: due.data.get(k) for k in TDS_DUE_KEYS}},
            "history": history}


def _amount(values: dict, key: str, errors: dict) -> Decimal:
    raw = values.get(key)
    if raw in (None, ""):
        return Decimal(0)
    try:
        value = D(raw)
    except Exception:
        errors[key] = "Enter an amount in rupees"
        return Decimal(0)
    if value < 0:
        errors[key] = "Cannot be negative"
    return value


def calculate(svc: PayrollService, on: date, values: dict) -> dict:
    """Compare both regimes for one annual salary and set of declarations."""
    errors: dict[str, str] = {}
    keys = ("annual_gross", "basic_da", "hra_received", "professional_tax", "employee_pf")
    amounts = {k: _amount(values, k, errors) for k in keys}
    decl = {k: _amount(values, k, errors) for k in DECLARATION_KEYS}
    if amounts["annual_gross"] <= 0 and "annual_gross" not in errors:
        errors["annual_gross"] = "Enter the yearly gross salary"
    for k in ("basic_da", "hra_received"):
        if amounts[k] > amounts["annual_gross"] and k not in errors:
            errors[k] = "Cannot be more than the gross salary"
    age_group = values.get("age_group") or "below_60"
    if age_group not in ("below_60", "60_to_80", "80_plus"):
        errors["age_group"] = "Choose below 60, 60 to 79 or 80 and above"
    if errors:
        raise ServiceError("Check the highlighted fields", errors=errors)
    salary = AnnualSalary(gross=amounts["annual_gross"], basic_da=amounts["basic_da"],
                          hra_received=amounts["hra_received"], professional_tax=amounts["professional_tax"],
                          employee_pf=amounts["employee_pf"])
    profile = {"age_group": age_group, "metro": bool(values.get("metro_city")),
               "parents_senior": bool(values.get("parents_senior")), "declarations": decl}
    results = {k: explain(k, salary, svc.rules.central(cat, on), **profile) for k, cat in CATEGORIES.items()}
    new, old = results["new"]["total_tax"], results["old"]["total_tax"]
    better = "new" if new <= old else "old"
    return {"on": on, "tax_year": tax_year_label(on), "new": results["new"], "old": results["old"],
            "better": better, "saving": abs(new - old)}

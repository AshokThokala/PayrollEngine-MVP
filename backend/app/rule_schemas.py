"""What each kind of compliance rule contains, and how to check a new rule.

The UI builds the "Add rule" form from these definitions, and the API uses them
to validate input, so a new rule can never be missing a value the engine needs.

Field types:
  money       amount in rupees (>= 0)
  percent     stored as a fraction (0.12 = 12%), between 0 and 1
  integer     whole number (>= 0)
  day         day of month, 1-31
  month       month number, 1-12
  mmdd        a date in the year as MM-DD, e.g. 04-30
  months      list of month numbers, e.g. [12]
  text_list   list of words, e.g. ["basic", "da"]
  amount_slabs  [{"upto": 15000, "amount": 0}, ..., {"upto": null, "amount": 200}]
  rate_slabs    [{"upto": 400000, "rate": 0}, ..., {"upto": null, "rate": 0.30}]
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

STATE_NAMES = {
    "AN": "Andaman and Nicobar Islands", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh",
    "AS": "Assam", "BR": "Bihar", "CH": "Chandigarh", "CG": "Chhattisgarh",
    "DH": "Dadra and Nagar Haveli and Daman and Diu", "DL": "Delhi", "GA": "Goa",
    "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep",
    "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur", "ML": "Meghalaya",
    "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha", "PY": "Puducherry", "PB": "Punjab",
    "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TG": "Telangana", "TR": "Tripura",
    "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal",
}


def f(key: str, label: str, type_: str, help_: str) -> dict:
    return {"key": key, "label": label, "type": type_, "help": help_}


CATEGORIES: dict[str, dict] = {
    "pf": {
        "label": "Provident Fund (EPF)", "scope": "central",
        "fields": [
            f("wage_ceiling", "Wage ceiling (₹/month)", "money", "PF is calculated on wages up to this amount unless PF on full wages is chosen."),
            f("employee_rate", "Employee contribution", "percent", "Deducted from the employee's PF wages."),
            f("employer_rate", "Employer contribution (total)", "percent", "Employer's total share; EPS is carved out of it."),
            f("eps_rate", "Pension (EPS) share", "percent", "Part of the employer share that goes to pension, always on wages up to the ceiling."),
            f("edli_rate", "EDLI", "percent", "Employer's insurance contribution on wages up to the ceiling."),
            f("admin_rate", "Admin charges", "percent", "Employer's EPF administration charges."),
        ],
    },
    "esi": {
        "label": "Employees' State Insurance (ESI)", "scope": "central",
        "fields": [
            f("eligibility_wage_limit", "Coverage wage limit (₹/month)", "money", "Employees earning up to this amount are covered."),
            f("employee_rate", "Employee contribution", "percent", "Deducted from gross wages, rounded up to the next rupee."),
            f("employer_rate", "Employer contribution", "percent", "Paid by the employer on gross wages."),
        ],
    },
    "wage_code": {
        "label": "Code on Wages – definition of wages", "scope": "central",
        "fields": [
            f("min_wage_share_of_total", "Minimum share counted as wages", "percent", "If allowances exceed the rest, the excess is added back to wages."),
            f("wage_components", "Components that are wages", "text_list", "Salary components counted as wages, e.g. basic, da, retaining_allowance."),
            f("fnf_settlement_working_days", "Full-and-final within (working days)", "integer", "Deadline to settle dues after an exit."),
        ],
    },
    "income_tax_new_regime": {
        "label": "Income tax – new regime (TDS on salary)", "scope": "central",
        "fields": [
            f("standard_deduction", "Standard deduction (₹/year)", "money", "Deducted from salary before applying slabs."),
            f("slabs", "Tax slabs", "rate_slabs", "Taxable income bands and their rates; the last band has no upper limit."),
            f("rebate_income_limit", "Rebate income limit (₹)", "money", "Tax is fully rebated up to this taxable income (with marginal relief above it)."),
            f("rebate_max", "Maximum rebate (₹)", "money", "Largest rebate allowed."),
            f("cess_rate", "Health and education cess", "percent", "Added on top of the tax."),
        ],
    },
    "filing_due_dates": {
        "label": "Filing due dates (PF, ESI, TDS, Form 24Q)", "scope": "central",
        "fields": [
            f("pf_due_day", "PF due day (next month)", "day", "Day of the following month by which PF must be paid."),
            f("esi_due_day", "ESI due day (next month)", "day", "Day of the following month by which ESI must be paid."),
            f("tds_due_day", "TDS due day (next month)", "day", "Day of the following month for TDS deposit (April to February)."),
            f("tds_march_due", "TDS due for March (MM-DD)", "mmdd", "Special due date for March deductions, e.g. 04-30."),
            f("form_24q_q1_due", "Form 24Q Q1 due (MM-DD)", "mmdd", "Quarter April–June."),
            f("form_24q_q2_due", "Form 24Q Q2 due (MM-DD)", "mmdd", "Quarter July–September."),
            f("form_24q_q3_due", "Form 24Q Q3 due (MM-DD)", "mmdd", "Quarter October–December."),
            f("form_24q_q4_due", "Form 24Q Q4 due (MM-DD)", "mmdd", "Quarter January–March."),
        ],
    },
    "professional_tax": {
        "label": "Professional Tax (state)", "scope": "state",
        "fields": [
            f("slabs", "Monthly slabs", "amount_slabs", "Monthly gross pay bands and the tax for each; the last band has no upper limit."),
            f("due_day", "Due day (next month)", "day", "Day of the following month by which PT must be paid."),
        ],
    },
    "lwf": {
        "label": "Labour Welfare Fund (state)", "scope": "state",
        "fields": [
            f("employee_amount", "Employee contribution (₹)", "money", "Deducted from the employee in each deduction month."),
            f("employer_amount", "Employer contribution (₹)", "money", "Paid by the employer in each deduction month."),
            f("deduction_months", "Deduction months", "months", "Pay months in which LWF is deducted, e.g. 12 for December."),
            f("due_month", "Payment due month", "month", "Month in which the contribution must be paid."),
            f("due_day", "Payment due day", "day", "Day of that month."),
        ],
    },
}

MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def _number(value) -> Decimal:
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("Enter a number")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Enter a number") from None


def _check_value(type_: str, value):
    """Return the cleaned value or raise ValueError with a readable message."""
    if type_ in ("money", "integer", "day", "month", "percent"):
        n = _number(value)
        if n < 0:
            raise ValueError("Must be 0 or more")
        if type_ == "percent":
            if n > 1:
                raise ValueError("Enter a fraction between 0 and 1 (e.g. 0.12 for 12%)")
            return float(n)
        if type_ == "money":
            return float(n) if n != n.to_integral_value() else int(n)
        if n != n.to_integral_value():
            raise ValueError("Enter a whole number")
        n = int(n)
        if type_ == "day" and not 1 <= n <= 31:
            raise ValueError("Enter a day between 1 and 31")
        if type_ == "month" and not 1 <= n <= 12:
            raise ValueError("Enter a month between 1 and 12")
        return n
    if type_ == "mmdd":
        if not isinstance(value, str) or not MMDD.match(value):
            raise ValueError("Enter as MM-DD, e.g. 04-30")
        return value
    if type_ == "months":
        if not isinstance(value, list) or not value:
            raise ValueError("Enter at least one month")
        return sorted({_check_value("month", m) for m in value})
    if type_ == "text_list":
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x.strip() for x in value):
            raise ValueError("Enter at least one name")
        return [x.strip() for x in value]
    if type_ in ("amount_slabs", "rate_slabs"):
        key = "amount" if type_ == "amount_slabs" else "rate"
        if not isinstance(value, list) or not value:
            raise ValueError("Add at least one slab")
        cleaned, last = [], Decimal(-1)
        for i, slab in enumerate(value, start=1):
            if not isinstance(slab, dict):
                raise ValueError(f"Slab {i}: invalid")
            upto = slab.get("upto")
            is_last = i == len(value)
            if is_last:
                if upto not in (None, ""):
                    raise ValueError("The last slab must have no upper limit")
                upto_clean = None
            else:
                try:
                    upto_n = _check_value("money", upto)
                except ValueError:
                    raise ValueError(f"Slab {i}: enter the upper limit") from None
                if Decimal(str(upto_n)) <= last:
                    raise ValueError(f"Slab {i}: upper limits must increase")
                last, upto_clean = Decimal(str(upto_n)), upto_n
            try:
                amount = _check_value("percent" if key == "rate" else "money", slab.get(key))
            except ValueError as exc:
                raise ValueError(f"Slab {i}: {exc}") from None
            cleaned.append({"upto": upto_clean, key: amount})
        return cleaned
    raise ValueError(f"Unknown field type {type_}")


def validate(category: str, scope: str, params: dict) -> tuple[dict, dict[str, str]]:
    """Return (cleaned params, {field key: error message})."""
    errors: dict[str, str] = {}
    spec = CATEGORIES.get(category)
    if spec is None:
        return {}, {"category": f"Choose one of: {', '.join(CATEGORIES)}"}
    if spec["scope"] == "central" and scope != "central":
        errors["scope"] = f"{spec['label']} is a central rule; scope must be 'central'"
    if spec["scope"] == "state" and scope not in STATE_NAMES:
        errors["scope"] = "Choose a state"
    cleaned = {}
    for field in spec["fields"]:
        key = field["key"]
        if key not in params:
            errors[key] = "This field is required"
            continue
        try:
            cleaned[key] = _check_value(field["type"], params[key])
        except ValueError as exc:
            errors[key] = str(exc)
    return cleaned, errors


def field_label(category: str, key: str) -> str:
    for field in CATEGORIES.get(category, {}).get("fields", []):
        if field["key"] == key:
            return field["label"]
    return {"scope": "Scope", "category": "Rule type", "valid_from": "Effective from",
            "source": "Source"}.get(key, key)

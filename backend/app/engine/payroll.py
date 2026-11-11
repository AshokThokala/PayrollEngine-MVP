"""Compute one employee's payslip for one month."""
from __future__ import annotations

import calendar
from datetime import date

from .models import Employee, Line, PayInputs, Payslip, SalaryStructure
from .money import ZERO, paise
from .rules import RuleBook, RuleNotFound
from .statutory import compute_esi, compute_lwf, compute_pf, compute_pt, esi_covered
from .tds import AnnualSalary, compute_annual, monthly_from_annual
from .wages import check_structure, statutory_wages

LABELS = {
    "basic": "Basic",
    "da": "Dearness allowance",
    "retaining_allowance": "Retaining allowance",
    "hra": "House rent allowance",
    "conveyance": "Conveyance",
    "special_allowance": "Special allowance",
}


def _label(code: str) -> str:
    return LABELS.get(code, code.replace("_", " ").capitalize())


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def compute_payslip(employee: Employee, structure: SalaryStructure,
                    inputs: PayInputs, rules: RuleBook) -> Payslip:
    on = month_end(inputs.period)
    wage_rule = rules.central("wage_code", on)
    warnings = check_structure(structure, wage_rule)

    # 1. Earnings, prorated for paid days.
    factor = inputs.paid_days / inputs.days_in_month
    earned = {k: paise(v * factor) for k, v in structure.components.items()}
    earnings = [Line(k, _label(k), v) for k, v in earned.items()]
    if inputs.overtime:
        earnings.append(Line("overtime", "Overtime", paise(inputs.overtime)))
    for code, amt in inputs.other_earnings.items():
        earnings.append(Line(code, _label(code), paise(amt)))
    gross = sum((l.amount for l in earnings), ZERO)

    # 2. Statutory wages under the Code on Wages (overtime excluded).
    wages = statutory_wages(earned, wage_rule)

    deductions: list[Line] = []
    employer: list[Line] = []

    # 3. Provident Fund.
    if employee.pf_member:
        pf = compute_pf(wages, rules.central("pf", on),
                        full_wages=employee.pf_on_full_wages,
                        eps_member=employee.eps_member)
        deductions.append(Line("pf_employee", "Provident fund", pf.employee, pf.rule))
        employer += [
            Line("pf_employer_epf", "Employer PF (EPF)", pf.employer_epf, pf.rule),
            Line("pf_employer_eps", "Employer pension (EPS)", pf.employer_eps, pf.rule),
            Line("pf_edli", "EDLI", pf.edli, pf.rule),
            Line("pf_admin", "PF admin charges", pf.admin, pf.rule),
        ]

    # 4. ESI (coverage decided on fixed monthly pay unless set on the employee).
    esi_rule = rules.central("esi", on)
    covered = (employee.esi_covered if employee.esi_covered is not None
               else esi_covered(structure.total, esi_rule))
    esi = compute_esi(gross, covered, esi_rule)
    if esi.covered:
        deductions.append(Line("esi_employee", "ESI", esi.employee, esi.rule))
        employer.append(Line("esi_employer", "Employer ESI", esi.employer, esi.rule))

    # 5. Professional tax and Labour Welfare Fund (state rules).
    if employee.pt_applicable:
        try:
            pt_rule = rules.state(employee.state, "professional_tax", on)
        except RuleNotFound:
            pt_rule = None
            warnings.append(f"No Professional Tax rule for {employee.state} on {on}; PT not deducted")
        pt = compute_pt(gross, pt_rule) if pt_rule else 0
        if pt:
            deductions.append(Line("pt", "Professional tax", pt, pt_rule.version))
    lwf_rule = None
    if employee.lwf_applicable:
        try:
            lwf_rule = rules.state(employee.state, "lwf", on)
        except RuleNotFound:
            warnings.append(f"No Labour Welfare Fund rule for {employee.state} on {on}; LWF not deducted")
    if lwf_rule:
        lwf_emp, lwf_er = compute_lwf(on.month, lwf_rule)
        if lwf_emp or lwf_er:
            deductions.append(Line("lwf_employee", "Labour welfare fund", lwf_emp, lwf_rule.version))
            employer.append(Line("lwf_employer", "Employer LWF", lwf_er, lwf_rule.version))

    # 6. TDS on salary (Income-tax Act 2025 s.392): project the year, tax it, spread the rest.
    regime = employee.tax_regime if employee.tax_regime in ("new", "old") else "new"
    tax_rule = rules.central(f"income_tax_{regime}_regime", on)
    months_left = 12 - inputs.fy_month_index + 1
    this_month = {line.code: line.amount for line in deductions}
    basic_da = sum((earned.get(k, ZERO) for k in ("basic", "da")), ZERO)
    annual = AnnualSalary(
        gross=inputs.ytd_taxable_gross + gross * months_left,
        basic_da=inputs.ytd_basic_da + basic_da * months_left,
        hra_received=inputs.ytd_hra + earned.get("hra", ZERO) * months_left,
        professional_tax=inputs.ytd_pt + this_month.get("pt", ZERO) * months_left,
        employee_pf=inputs.ytd_pf + this_month.get("pf_employee", ZERO) * months_left,
    )
    tax = compute_annual(regime, annual, tax_rule, age_group=employee.tax_age_group,
                         metro=employee.metro_city, parents_senior=employee.parents_senior,
                         declarations=employee.tax_declarations)
    tds = monthly_from_annual(tax.tax, inputs.ytd_tds, months_left)
    if tds:
        deductions.append(Line("tds", f"Income tax (TDS, {regime} regime)", tds, tax_rule.version))

    # 7. Other deductions (advances, canteen, ...).
    for code, amt in inputs.other_deductions.items():
        deductions.append(Line(code, _label(code), paise(amt)))

    slip = Payslip(employee.code, on, earnings, deductions, employer, warnings, wages)
    if slip.net_pay < 0:
        slip.warnings.append("Net pay is negative; review deductions before approval")
    return slip

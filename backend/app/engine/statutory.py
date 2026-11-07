"""PF, ESI, Professional Tax and Labour Welfare Fund calculations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import D, ZERO, rupee, rupee_up
from .rules import Rule


@dataclass
class PFResult:
    pf_wages: Decimal
    employee: Decimal
    employer_epf: Decimal
    employer_eps: Decimal
    edli: Decimal
    admin: Decimal
    rule: str


def compute_pf(wages: Decimal, rule: Rule, *, full_wages: bool = False,
               eps_member: bool = True) -> PFResult:
    ceiling = D(rule["wage_ceiling"])
    capped = min(wages, ceiling)
    pf_wages = wages if full_wages else capped
    employee = rupee(pf_wages * D(rule["employee_rate"]))
    employer_total = rupee(pf_wages * D(rule["employer_rate"]))
    # Pension is always on wages up to the ceiling.
    eps = rupee(capped * D(rule["eps_rate"])) if eps_member else ZERO
    return PFResult(
        pf_wages=pf_wages,
        employee=employee,
        employer_epf=employer_total - eps,
        employer_eps=eps,
        edli=rupee(capped * D(rule["edli_rate"])),
        admin=rupee(pf_wages * D(rule["admin_rate"])),
        rule=rule.version,
    )


@dataclass
class ESIResult:
    covered: bool
    esi_wages: Decimal
    employee: Decimal
    employer: Decimal
    rule: str


def esi_covered(fixed_monthly_wages: Decimal, rule: Rule) -> bool:
    return fixed_monthly_wages <= D(rule["eligibility_wage_limit"])


def compute_esi(gross_earned: Decimal, covered: bool, rule: Rule) -> ESIResult:
    if not covered or gross_earned <= 0:
        return ESIResult(covered, ZERO, ZERO, ZERO, rule.version)
    return ESIResult(
        covered=True,
        esi_wages=gross_earned,
        employee=rupee_up(gross_earned * D(rule["employee_rate"])),
        employer=rupee_up(gross_earned * D(rule["employer_rate"])),
        rule=rule.version,
    )


def compute_pt(gross_earned: Decimal, rule: Rule) -> Decimal:
    for slab in rule["slabs"]:
        if slab["upto"] is None or gross_earned <= D(slab["upto"]):
            return D(slab["amount"])
    raise ValueError("Professional tax slabs must end with an open slab")


def compute_lwf(month: int, rule: Rule) -> tuple[Decimal, Decimal]:
    """Return (employee, employer) LWF for this pay month."""
    if month in rule["deduction_months"]:
        return D(rule["employee_amount"]), D(rule["employer_amount"])
    return ZERO, ZERO

"""Income tax on salary and monthly TDS (Income-tax Act 2025, s.392; formerly s.192).

Method (projection): estimate the year's salary from what has been paid so far plus
this month's pay for the remaining months, work out the year's tax under the
employee's regime, then spread what is still unpaid over the months left.

Covered:
  - New regime (default): standard deduction, slabs, rebate with marginal relief,
    surcharge (max 25%) with marginal relief, cess.
  - Old regime: age-based slabs (below 60 / 60-79 / 80+), standard deduction,
    professional tax (max ₹2,500), HRA exemption, 80C (incl. employee PF),
    80CCD(1B), 80D (self and parents, senior limits), home loan interest,
    rebate, surcharge (up to 37%) with marginal relief, cess.
Not covered yet: perquisites, employer NPS 80CCD(2), other income, previous employer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .money import D, ZERO, rupee
from .rules import Rule

PT_DEDUCTION_CAP = Decimal(2500)  # professional tax deductible from salary, per year
AGE_SLABS = {"below_60": "slabs_below_60", "60_to_80": "slabs_60_to_80", "80_plus": "slabs_80_plus"}
DECLARATION_KEYS = ("rent_paid", "sec_80c", "sec_80ccd_1b", "sec_80d_self",
                    "sec_80d_parents", "home_loan_interest")


@dataclass
class AnnualSalary:
    """Projected figures for the whole financial year (rupees)."""

    gross: Decimal
    basic_da: Decimal = ZERO      # salary for HRA purposes
    hra_received: Decimal = ZERO
    professional_tax: Decimal = ZERO
    employee_pf: Decimal = ZERO   # counts towards 80C


@dataclass
class TaxResult:
    regime: str
    taxable_income: Decimal
    tax: Decimal                   # after rebate, surcharge and cess
    deductions: list[tuple[str, Decimal]] = field(default_factory=list)


def slab_tax(income: Decimal, slabs: list[dict], rate_key: str = "rate") -> Decimal:
    tax, lower = ZERO, ZERO
    for slab in slabs:
        upper = None if slab["upto"] is None else D(slab["upto"])
        top = income if upper is None else min(income, upper)
        if top > lower:
            tax += (top - lower) * D(slab[rate_key])
        if upper is None or income <= upper:
            break
        lower = upper
    return tax


def _bracket(income: Decimal, slabs: list[dict]) -> tuple[Decimal, Decimal, Decimal]:
    """(rate for this income, lower limit of its band, rate of the band below)."""
    lower, prev_rate = ZERO, ZERO
    for slab in slabs:
        upper = None if slab["upto"] is None else D(slab["upto"])
        if upper is None or income <= upper:
            return D(slab["rate"]), lower, prev_rate
        lower, prev_rate = upper, D(slab["rate"])
    return ZERO, ZERO, ZERO


def with_surcharge(income: Decimal, tax_before: Decimal, tax_fn, slabs: list[dict] | None) -> Decimal:
    """Tax plus surcharge, limited by marginal relief at the band's lower limit."""
    if not slabs:
        return tax_before
    rate, threshold, prev_rate = _bracket(income, slabs)
    total = tax_before * (1 + rate)
    if rate and threshold:
        ceiling = tax_fn(threshold) * (1 + prev_rate) + (income - threshold)
        total = min(total, ceiling)
    return total


def _new_regime_tax(taxable: Decimal, rule: Rule) -> Decimal:
    tax = slab_tax(taxable, rule["slabs"])
    limit = D(rule["rebate_income_limit"])
    if taxable <= limit:
        return max(ZERO, tax - D(rule["rebate_max"]))
    return min(tax, taxable - limit)  # marginal relief just above the rebate limit


def _old_regime_tax(taxable: Decimal, rule: Rule, age_group: str) -> Decimal:
    tax = slab_tax(taxable, rule[AGE_SLABS.get(age_group, "slabs_below_60")])
    if taxable <= D(rule["rebate_income_limit"]):
        tax -= min(tax, D(rule["rebate_max"]))
    return tax


def annual_tax(regime: str, taxable: Decimal, rule: Rule, age_group: str = "below_60") -> Decimal:
    if regime == "old":
        def base(x):
            return _old_regime_tax(x, rule, age_group)
    else:
        def base(x):
            return _new_regime_tax(x, rule)
    total = with_surcharge(taxable, base(taxable), base, rule.data.get("surcharge_slabs"))
    return rupee(total * (1 + D(rule["cess_rate"])))


def taxable_income(regime: str, salary: AnnualSalary, rule: Rule, *, age_group: str = "below_60",
                   metro: bool = False, parents_senior: bool = False,
                   declarations: dict | None = None) -> tuple[Decimal, list[tuple[str, Decimal]]]:
    decl = {k: D((declarations or {}).get(k, 0)) for k in DECLARATION_KEYS}
    items: list[tuple[str, Decimal]] = [
        ("Standard deduction", min(salary.gross, D(rule["standard_deduction"])))]
    if regime == "old":
        items.append(("Professional tax", min(salary.professional_tax, PT_DEDUCTION_CAP)))
        if decl["rent_paid"] > 0 and salary.hra_received > 0:
            share = D(rule["hra_metro_share" if metro else "hra_non_metro_share"])
            hra = min(salary.hra_received, decl["rent_paid"] - salary.basic_da / 10,
                      salary.basic_da * share)
            items.append(("HRA exemption", max(ZERO, hra)))
        senior = age_group != "below_60"
        items += [
            ("80C (incl. employee PF)", min(decl["sec_80c"] + salary.employee_pf, D(rule["limit_80c"]))),
            ("80CCD(1B) NPS", min(decl["sec_80ccd_1b"], D(rule["limit_80ccd_1b"]))),
            ("80D self/family", min(decl["sec_80d_self"],
                                    D(rule["limit_80d_self_senior" if senior else "limit_80d_self"]))),
            ("80D parents", min(decl["sec_80d_parents"],
                                D(rule["limit_80d_parents_senior" if parents_senior else "limit_80d_parents"]))),
            ("Home loan interest", min(decl["home_loan_interest"], D(rule["limit_home_loan_interest"]))),
        ]
    items = [(label, rupee(v)) for label, v in items if v > 0]
    return max(ZERO, salary.gross - sum((v for _, v in items), ZERO)), items


def compute_annual(regime: str, salary: AnnualSalary, rule: Rule, **profile) -> TaxResult:
    taxable, items = taxable_income(regime, salary, rule, **profile)
    return TaxResult(regime, taxable, annual_tax(regime, taxable, rule, profile.get("age_group", "below_60")), items)


def monthly_from_annual(annual: Decimal, ytd_tds: Decimal, months_left: int) -> Decimal:
    remaining = annual - ytd_tds
    return ZERO if remaining <= 0 else rupee(remaining / months_left)


# --- kept for the simple new-regime callers and tests --------------------------------

def annual_tax_new_regime(annual_gross: Decimal, rule: Rule) -> Decimal:
    taxable, _ = taxable_income("new", AnnualSalary(gross=D(annual_gross)), rule)
    return annual_tax("new", taxable, rule)


def monthly_tds(current_month_gross: Decimal, fy_month_index: int,
                ytd_gross: Decimal, ytd_tds: Decimal, rule: Rule) -> Decimal:
    months_left = 12 - fy_month_index + 1
    projected = ytd_gross + current_month_gross * months_left
    return monthly_from_annual(annual_tax_new_regime(projected, rule), ytd_tds, months_left)


# --- explained calculation (Tax rules page calculator) --------------------------------

def slab_breakdown(income: Decimal, slabs: list[dict]) -> list[dict]:
    """Tax in each band: [{'from', 'upto', 'rate', 'taxed', 'tax'}]."""
    rows, lower = [], ZERO
    for slab in slabs:
        upper = None if slab["upto"] is None else D(slab["upto"])
        top = income if upper is None else min(income, upper)
        taxed = max(ZERO, top - lower)
        rows.append({"from": lower, "upto": upper, "rate": D(slab["rate"]), "taxed": rupee(taxed),
                     "tax": rupee(taxed * D(slab["rate"]))})
        if upper is None or income <= upper:
            break
        lower = upper
    return rows


def explain(regime: str, salary: AnnualSalary, rule: Rule, **profile) -> dict:
    """Every step of the year's tax: deductions, slabs, rebate, surcharge, cess, monthly TDS."""
    age_group = profile.get("age_group", "below_60")
    taxable, items = taxable_income(regime, salary, rule, **profile)
    slabs = rule[AGE_SLABS.get(age_group, "slabs_below_60")] if regime == "old" else rule["slabs"]
    on_slabs = slab_tax(taxable, slabs)
    if regime == "old":
        def base(x):
            return _old_regime_tax(x, rule, age_group)
    else:
        def base(x):
            return _new_regime_tax(x, rule)
    after_rebate = base(taxable)
    with_sur = with_surcharge(taxable, after_rebate, base, rule.data.get("surcharge_slabs"))
    total = annual_tax(regime, taxable, rule, age_group)
    rebate, surcharge = rupee(on_slabs - after_rebate), rupee(with_sur - after_rebate)
    return {
        "regime": regime, "rule_version": rule.version, "gross": rupee(salary.gross),
        "deductions": [{"label": k, "amount": v} for k, v in items],
        "total_deductions": sum((v for _, v in items), ZERO), "taxable_income": rupee(taxable),
        "slabs": slab_breakdown(taxable, slabs), "tax_on_slabs": rupee(on_slabs),
        "rebate": rebate, "surcharge": surcharge,
        "cess": total - rupee(on_slabs) + rebate - surcharge, "total_tax": total,
        "monthly_tds": rupee(total / 12),
        "effective_rate": (total / salary.gross).quantize(Decimal("0.0001")) if salary.gross else ZERO,
    }

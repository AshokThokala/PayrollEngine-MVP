"""TDS on salary, new tax regime (projection method).

Monthly TDS = (projected annual tax - TDS already deducted this FY)
              / months left in the FY including this one.

Simplified for the MVP: no other income, no employer NPS, no perquisites.
The old regime is not supported yet.
"""
from __future__ import annotations

from decimal import Decimal

from .money import D, ZERO, rupee
from .rules import Rule


def annual_tax_new_regime(annual_gross: Decimal, rule: Rule) -> Decimal:
    taxable = max(ZERO, annual_gross - D(rule["standard_deduction"]))
    tax = ZERO
    lower = ZERO
    for slab in rule["slabs"]:
        upper = None if slab["upto"] is None else D(slab["upto"])
        top = taxable if upper is None else min(taxable, upper)
        if top > lower:
            tax += (top - lower) * D(slab["rate"])
        if upper is None or taxable <= upper:
            break
        lower = upper

    limit = D(rule["rebate_income_limit"])
    if taxable <= limit:
        tax = max(ZERO, tax - D(rule["rebate_max"]))
    else:
        # Marginal relief: tax may not exceed the income above the rebate limit.
        tax = min(tax, taxable - limit)

    return rupee(tax * (1 + D(rule["cess_rate"])))


def monthly_tds(current_month_gross: Decimal, fy_month_index: int,
                ytd_gross: Decimal, ytd_tds: Decimal, rule: Rule) -> Decimal:
    months_left = 12 - fy_month_index + 1
    projected = ytd_gross + current_month_gross * months_left
    annual = annual_tax_new_regime(projected, rule)
    remaining = annual - ytd_tds
    if remaining <= 0:
        return ZERO
    return rupee(remaining / months_left)

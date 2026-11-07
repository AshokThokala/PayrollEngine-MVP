"""Code on Wages: the uniform definition of "wages".

Wages = basic + DA + retaining allowance. If the excluded components
(HRA, conveyance, special allowance, ...) exceed 50% of total remuneration,
the excess is added back to wages. Statutory contributions (PF, gratuity,
bonus) are computed on these wages.
"""
from __future__ import annotations

from decimal import Decimal

from .models import SalaryStructure
from .money import ZERO, paise
from .rules import Rule


def statutory_wages(components: dict[str, Decimal], rule: Rule) -> Decimal:
    share = Decimal(str(rule["min_wage_share_of_total"]))
    included = set(rule["wage_components"])
    total = sum(components.values(), ZERO)
    core = sum((v for k, v in components.items() if k in included), ZERO)
    excluded = total - core
    cap = total * (1 - share)
    add_back = excluded - cap if excluded > cap else ZERO
    return paise(core + add_back)


def check_structure(structure: SalaryStructure, rule: Rule) -> list[str]:
    """Warnings to show before a salary structure is saved."""
    warnings: list[str] = []
    total = structure.total
    if total <= 0:
        return ["Salary structure total must be greater than zero"]
    included = set(rule["wage_components"])
    core = sum((v for k, v in structure.components.items() if k in included), ZERO)
    share = core / total
    minimum = Decimal(str(rule["min_wage_share_of_total"]))
    if share < minimum:
        warnings.append(
            f"Basic + DA + retaining allowance is {share:.0%} of total pay; the Code on "
            f"Wages treats at least {minimum:.0%} as wages. PF and gratuity will be "
            f"calculated on {statutory_wages(structure.components, rule)} rather than {core}."
        )
    return warnings

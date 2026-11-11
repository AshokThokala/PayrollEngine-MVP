"""Income tax: both regimes, surcharge with marginal relief, old-regime deductions."""
from datetime import date
from decimal import Decimal

import pytest

from app.engine import RuleBook
from app.engine.tds import AnnualSalary, annual_tax, compute_annual

RULES = RuleBook.load()
TY = date(2026, 10, 31)  # Tax Year 2026-27
NEW = RULES.central("income_tax_new_regime", TY)
OLD = RULES.central("income_tax_old_regime", TY)
D = Decimal


@pytest.mark.parametrize("taxable,expected", [
    (1200000, 0),           # fully rebated
    (1225000, 26000),       # marginal relief above 12 lakh
    (2400000, 312000),
    (5010000, 1133600),     # surcharge 10%, marginal relief at 50 lakh
    (6000000, 1578720),     # surcharge 10%, no relief needed
])
def test_new_regime(taxable, expected):
    assert annual_tax("new", D(taxable), NEW) == D(expected)


def test_new_regime_surcharge_capped_at_25_percent():
    assert NEW["surcharge_slabs"][-1]["rate"] == 0.25
    assert OLD["surcharge_slabs"][-1]["rate"] == 0.37


@pytest.mark.parametrize("taxable,age,expected", [
    (500000, "below_60", 0),            # rebate 12,500
    (500100, "below_60", 13021),        # no marginal relief in the old regime
    (1000000, "60_to_80", 114400),      # 3 lakh exemption
    (1000000, "80_plus", 104000),       # 5 lakh exemption
])
def test_old_regime_by_age(taxable, age, expected):
    assert annual_tax("old", D(taxable), OLD, age) == D(expected)


def test_old_regime_deductions():
    salary = AnnualSalary(gross=D(1200000), basic_da=D(600000), hra_received=D(240000),
                          professional_tax=D(2400), employee_pf=D(72000))
    result = compute_annual("old", salary, OLD, age_group="below_60", metro=True, parents_senior=True,
                            declarations={"rent_paid": 240000, "sec_80c": 100000, "sec_80ccd_1b": 50000,
                                          "sec_80d_self": 30000, "sec_80d_parents": 30000})
    assert dict(result.deductions) == {
        "Standard deduction": 50000, "Professional tax": 2400, "HRA exemption": 180000,
        "80C (incl. employee PF)": 150000, "80CCD(1B) NPS": 50000,
        "80D self/family": 25000, "80D parents": 30000}
    assert result.taxable_income == D(712600)
    assert result.tax == D(57221)


def test_new_regime_ignores_old_regime_deductions():
    salary = AnnualSalary(gross=D(1200000), hra_received=D(240000), professional_tax=D(2400))
    result = compute_annual("new", salary, NEW, declarations={"sec_80c": 150000, "rent_paid": 300000})
    assert dict(result.deductions) == {"Standard deduction": 75000}
    assert result.tax == 0

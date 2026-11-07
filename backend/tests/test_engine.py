from datetime import date
from decimal import Decimal

import pytest

from app.engine import Employee, PayInputs, RuleBook, RuleNotFound, SalaryStructure, compute_payslip
from app.engine.statutory import compute_esi, compute_lwf, compute_pf, compute_pt
from app.engine.tds import annual_tax_new_regime, monthly_tds
from app.engine.wages import check_structure, statutory_wages

RULES = RuleBook.load()
OCT_2026 = date(2026, 10, 31)
AUG_2026 = date(2026, 8, 31)


def d(x):
    return Decimal(str(x))


# --- Rule lookup -------------------------------------------------------------

def test_rule_versions_follow_dates():
    assert RULES.central("pf", AUG_2026)["wage_ceiling"] == 15000
    assert RULES.central("pf", date(2026, 9, 17))["wage_ceiling"] == 25000
    assert RULES.central("pf", OCT_2026).version == "central.pf@2026-09-17"


def test_unsupported_state_raises():
    with pytest.raises(RuleNotFound):
        RULES.state("KA", "professional_tax", OCT_2026)


# --- Code on Wages -----------------------------------------------------------

def test_wages_add_back_excess_allowances():
    rule = RULES.central("wage_code", OCT_2026)
    comps = {"basic": d(10000), "hra": d(6000), "special_allowance": d(9000)}
    # Allowances 15,000 exceed 50% of 25,000 by 2,500 -> added to wages.
    assert statutory_wages(comps, rule) == d(12500)


def test_wages_when_basic_is_half_or_more():
    rule = RULES.central("wage_code", OCT_2026)
    comps = {"basic": d(15000), "hra": d(6000), "special_allowance": d(4000)}
    assert statutory_wages(comps, rule) == d(15000)


def test_structure_warning_below_fifty_percent():
    rule = RULES.central("wage_code", OCT_2026)
    warnings = check_structure(SalaryStructure({"basic": 8000, "special_allowance": 12000}), rule)
    assert len(warnings) == 1 and "40%" in warnings[0]


# --- PF ----------------------------------------------------------------------

def test_pf_new_ceiling():
    pf = compute_pf(d(30000), RULES.central("pf", OCT_2026))
    assert (pf.employee, pf.employer_eps, pf.employer_epf) == (d(3000), d(2083), d(917))
    assert (pf.edli, pf.admin) == (d(125), d(125))


def test_pf_old_ceiling():
    pf = compute_pf(d(30000), RULES.central("pf", AUG_2026))
    assert (pf.employee, pf.employer_eps, pf.employer_epf) == (d(1800), d(1250), d(550))


def test_pf_voluntary_full_wages_keeps_eps_capped():
    pf = compute_pf(d(30000), RULES.central("pf", OCT_2026), full_wages=True)
    assert (pf.employee, pf.employer_eps, pf.employer_epf, pf.admin) == (d(3600), d(2083), d(1517), d(150))


def test_pf_without_eps():
    pf = compute_pf(d(10000), RULES.central("pf", OCT_2026), eps_member=False)
    assert (pf.employer_eps, pf.employer_epf) == (d(0), d(1200))


# --- ESI, PT, LWF ------------------------------------------------------------

def test_esi_rounds_up():
    rule = RULES.central("esi", OCT_2026)
    r = compute_esi(d(20001), True, rule)
    assert (r.employee, r.employer) == (d(151), d(651))
    assert compute_esi(d(18000), True, rule).employee == d(135)
    assert compute_esi(d(18000), False, rule).employee == d(0)


@pytest.mark.parametrize("gross,expected", [(15000, 0), (15001, 150), (20000, 150), (20001, 200)])
def test_telangana_pt(gross, expected):
    assert compute_pt(d(gross), RULES.state("TG", "professional_tax", OCT_2026)) == d(expected)


def test_telangana_lwf_once_a_year():
    rule = RULES.state("TG", "lwf", OCT_2026)
    assert compute_lwf(12, rule) == (d(2), d(5))
    assert compute_lwf(11, rule) == (d(0), d(0))


# --- TDS (new regime) --------------------------------------------------------

@pytest.mark.parametrize("annual_gross,tax", [
    (1275000, 0),         # taxable exactly 12 lakh: full rebate
    (1300000, 26000),     # marginal relief: 25,000 + 4% cess
    (2475000, 312000),    # taxable 24 lakh
])
def test_annual_tax(annual_gross, tax):
    rule = RULES.central("income_tax_new_regime", OCT_2026)
    assert annual_tax_new_regime(d(annual_gross), rule) == d(tax)


def test_monthly_tds_projection():
    rule = RULES.central("income_tax_new_regime", OCT_2026)
    assert monthly_tds(d(100000), 1, d(0), d(0), rule) == d(0)
    assert monthly_tds(d(200000), 1, d(0), d(0), rule) == d(24375)


# --- Full payslip ------------------------------------------------------------

def _emp(**kw):
    return Employee(code="E001", name="Ravi Kumar", **kw)


def test_full_month_payslip():
    slip = compute_payslip(
        _emp(),
        SalaryStructure({"basic": 15000, "hra": 6000, "special_allowance": 4000}),
        PayInputs(period=OCT_2026, days_in_month=31, paid_days=31,
                  fy_month_index=7, ytd_taxable_gross=150000),
        RULES,
    )
    assert slip.gross == d(25000)
    assert slip.statutory_wages == d(15000)
    assert slip.amount("pf_employee") == d(1800)
    assert slip.amount("esi_employee") == d(0)  # 25,000 is above the ESI limit
    assert slip.amount("pt") == d(200)
    assert slip.amount("tds") == d(0)
    assert slip.net_pay == d(23000)
    assert slip.employer_cost == d(26950)
    assert slip.warnings == []


def test_prorated_payslip():
    slip = compute_payslip(
        _emp(),
        SalaryStructure({"basic": 15000, "hra": 6000, "special_allowance": 4000}),
        PayInputs(period=OCT_2026, days_in_month=31, paid_days="15.5"),
        RULES,
    )
    assert slip.gross == d(12500)
    assert slip.amount("pf_employee") == d(900)
    assert slip.amount("pt") == d(0)
    assert slip.net_pay == d(11600)


def test_worker_payslip_with_esi_and_lwf():
    slip = compute_payslip(
        _emp(),
        SalaryStructure({"basic": 10000, "hra": 4000, "special_allowance": 4000}),
        PayInputs(period=date(2026, 12, 31), days_in_month=31, paid_days=31, fy_month_index=9),
        RULES,
    )
    assert slip.amount("pf_employee") == d(1200)
    assert slip.amount("pf_employer_eps") == d(833)
    assert slip.amount("esi_employee") == d(135)
    assert slip.amount("esi_employer") == d(585)
    assert slip.amount("pt") == d(150)
    assert slip.amount("lwf_employee") == d(2)
    assert slip.net_pay == d(16513)


def test_every_statutory_line_records_its_rule():
    slip = compute_payslip(
        _emp(),
        SalaryStructure({"basic": 10000, "hra": 4000, "special_allowance": 4000}),
        PayInputs(period=date(2026, 12, 31), days_in_month=31, paid_days=31),
        RULES,
    )
    statutory = [l for l in (*slip.deductions, *slip.employer_contributions)]
    assert statutory and all(l.rule for l in statutory)


def test_negative_net_pay_warns():
    slip = compute_payslip(
        _emp(),
        SalaryStructure({"basic": 10000}),
        PayInputs(period=OCT_2026, days_in_month=31, paid_days=31,
                  other_deductions={"advance_recovery": 20000}),
        RULES,
    )
    assert any("negative" in w for w in slip.warnings)

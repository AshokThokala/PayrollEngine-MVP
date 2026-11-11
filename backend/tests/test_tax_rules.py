"""Tax rules page: rules in force and the regime calculator."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import PayrollService, ServiceError
from app.services import tax

ON = date(2026, 11, 10)


@pytest.fixture
def svc(repo):
    s = PayrollService(repo, clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc))
    s.ensure_rules_seeded()
    return s


def test_overview(svc):
    o = tax.overview(svc, ON)
    assert o["tax_year"] == "2026-27"
    new = o["regimes"]["new"]["params"]
    assert new["standard_deduction"] == 75000 and new["slabs"][0]["upto"] == 400000
    assert o["regimes"]["old"]["params"]["limit_80c"] == 150000
    assert o["due_dates"]["tds_due_day"] == 7 and o["due_dates"]["tds_march_due"] == "04-30"
    assert {h["regime"] for h in o["history"]} == {"new", "old"}


def test_rebate_wipes_tax_up_to_12_75_lakh_gross(svc):
    r = tax.calculate(svc, ON, {"annual_gross": "1275000"})
    assert r["new"]["taxable_income"] == Decimal(1200000)
    assert r["new"]["tax_on_slabs"] == Decimal(60000) and r["new"]["rebate"] == Decimal(60000)
    assert r["new"]["total_tax"] == 0 and r["better"] == "new"


def test_breakdown_adds_up_and_old_regime_deductions(svc):
    r = tax.calculate(svc, ON, {"annual_gross": "2000000", "basic_da": "800000", "hra_received": "400000",
                                "rent_paid": "360000", "sec_80c": "150000", "sec_80d_self": "25000",
                                "home_loan_interest": "0", "professional_tax": "2500", "metro_city": True})
    new, old = r["new"], r["old"]
    # new: 20,00,000 - 75,000 = 19,25,000 -> 20,000 + 40,000 + 60,000 + 65,000 = 1,85,000 + 4% cess
    assert new["taxable_income"] == Decimal(1925000) and new["tax_on_slabs"] == Decimal(185000)
    assert new["total_tax"] == Decimal(192400)
    assert sum(s["tax"] for s in new["slabs"]) == new["tax_on_slabs"]
    labels = {d["label"] for d in old["deductions"]}
    assert {"HRA exemption", "80C (incl. employee PF)", "80D self/family", "Professional tax"} <= labels
    # old: 50,000 std + 2,500 PT + 2,80,000 HRA + 1,50,000 80C + 25,000 80D = 5,07,500 -> taxable 14,92,500
    assert old["total_deductions"] == Decimal(507500) and old["taxable_income"] == Decimal(1492500)
    assert old["total_tax"] == Decimal(270660) and r["better"] == "new"
    assert r["saving"] == abs(new["total_tax"] - old["total_tax"])


def test_calculator_validation(svc):
    with pytest.raises(ServiceError) as e:
        tax.calculate(svc, ON, {"annual_gross": "", "sec_80c": "-5", "basic_da": "abc", "age_group": "x"})
    assert set(e.value.errors) == {"annual_gross", "sec_80c", "basic_da", "age_group"}

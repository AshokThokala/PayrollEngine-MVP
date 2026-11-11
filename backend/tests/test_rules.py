"""Compliance rules stored in the repository and added through the service."""
from datetime import date, datetime, timezone

import pytest

from app import rule_schemas
from app.domain import Client, EmployeeRecord
from app.engine import Employee, SalaryStructure
from app.services import PayrollService, ServiceError


def service(repo):
    svc = PayrollService(repo, clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.ensure_rules_seeded()
    return svc


def test_seed_loads_every_default_rule_once(repo):
    svc = service(repo)
    keys = {(r.scope, r.category) for r in repo.list_rules()}
    assert keys == {("central", "pf"), ("central", "esi"), ("central", "wage_code"),
                    ("central", "income_tax_new_regime"), ("central", "income_tax_old_regime"),
                    ("central", "filing_due_dates"),
                    ("TG", "professional_tax"), ("TG", "lwf")}
    assert len(repo.list_rules()) == 9  # PF has two versions
    assert svc.ensure_rules_seeded() == 0
    assert svc.rules.central("pf", date(2026, 10, 31))["wage_ceiling"] == 25000


def test_every_seeded_rule_passes_validation(repo):
    service(repo)
    for rule in repo.list_rules():
        _, errors = rule_schemas.validate(rule.category, rule.scope, rule.params)
        assert errors == {}, (rule.id, errors)


def test_new_version_closes_previous_and_is_used(repo):
    svc = service(repo)
    old = svc.rules.state("TG", "professional_tax", date(2026, 10, 31))
    params = {"slabs": [{"upto": 15000, "amount": 0}, {"upto": 25000, "amount": 150},
                        {"upto": None, "amount": 250}], "due_day": 10}
    rule, closed = svc.add_rule("TG", "professional_tax", date(2027, 4, 1), params, "G.O. test", "ops1")
    assert closed.valid_to == date(2027, 3, 31)
    assert svc.rules.state("TG", "professional_tax", date(2027, 3, 31)).version == old.version
    assert svc.rules.state("TG", "professional_tax", date(2027, 4, 30)).version == rule.id.replace(":", ".", 1).replace(":", "@")
    assert repo.audit_log()[-1].action == "rule.create"


def test_cannot_insert_before_latest_version(repo):
    svc = service(repo)
    params = svc.rules.central("esi", date(2026, 10, 31)).data
    with pytest.raises(ServiceError) as exc:
        svc.add_rule("central", "esi", date(2019, 7, 1), params, "dup", "ops1")
    assert exc.value.field == "valid_from"


def test_validation_names_each_bad_field(repo):
    svc = service(repo)
    with pytest.raises(ServiceError) as exc:
        svc.add_rule("central", "esi", date(2027, 1, 1),
                     {"eligibility_wage_limit": -1, "employee_rate": 7.5}, "", "ops1")
    assert set(exc.value.errors) == {"eligibility_wage_limit", "employee_rate", "employer_rate", "source"}
    with pytest.raises(ServiceError) as exc:
        svc.add_rule("XX", "lwf", date(2027, 1, 1), {}, "x", "ops1")
    assert "scope" in exc.value.errors


def test_slab_rules():
    _, errors = rule_schemas.validate("professional_tax", "TG", {
        "slabs": [{"upto": 20000, "amount": 0}, {"upto": 15000, "amount": 150}, {"upto": 5, "amount": 200}],
        "due_day": 40})
    assert errors["due_day"] == "Enter a day between 1 and 31"
    assert errors["slabs"] == "Slab 2: upper limits must increase"


def test_new_state_becomes_usable_without_lwf_rule(repo):
    svc = service(repo)
    with pytest.raises(ServiceError):
        svc.add_client(Client(id="blr", legal_name="BLR Co", state="KA"), "ops1")
    svc.add_rule("KA", "professional_tax", date(2025, 4, 1),
                 {"slabs": [{"upto": 24999, "amount": 0}, {"upto": None, "amount": 200}], "due_day": 20},
                 "Karnataka PT - test", "ops1")
    svc.add_client(Client(id="blr", legal_name="BLR Co", state="KA"), "ops1")
    svc.add_employee(EmployeeRecord("blr", Employee(code="K1", name="Kiran"),
                                    SalaryStructure({"basic": 30000}), date(2026, 4, 1)), "ops1")
    run = svc.create_draft("blr", date(2026, 10, 1), user="ops1")
    assert run.slips["K1"].amount("pt") == 200
    assert any("No Labour Welfare Fund rule for KA" in f for f in run.flags)
    svc.approve(run.id, "reviewer")
    pt_filing = next(f for f in svc.lock(run.id, "reviewer") if f.kind == "pt")
    assert pt_filing.due_on == date(2026, 11, 20)


def test_seed_fills_new_fields_without_overwriting(repo):
    svc = PayrollService(repo, clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.ensure_rules_seeded()
    rule = next(r for r in repo.list_rules() if r.category == "income_tax_new_regime")
    rule.params = {k: v for k, v in rule.params.items() if k != "surcharge_slabs"}
    rule.params["cess_rate"] = 0.05  # a value someone edited
    repo.save_rule(rule)
    assert svc.ensure_rules_seeded() == 1
    again = next(r for r in repo.list_rules() if r.category == "income_tax_new_regime")
    assert again.params["surcharge_slabs"][-1]["rate"] == 0.25
    assert again.params["cess_rate"] == 0.05


def test_edit_rule_changes_values_and_is_audited(repo):
    svc = service(repo)
    rule = next(r for r in repo.list_rules() if r.scope == "TG" and r.category == "professional_tax")
    params = {**rule.params, "due_day": 12}
    edited = svc.edit_rule(rule.id, params, "Corrected due date", "ops1")
    assert edited.params["due_day"] == 12 and edited.valid_from == rule.valid_from
    assert svc.rules.state("TG", "professional_tax", date(2026, 10, 31))["due_day"] == 12
    assert repo.audit_log()[-1].detail == "changed: due_day, source"
    with pytest.raises(ServiceError) as exc:
        svc.edit_rule(rule.id, {**params, "due_day": 0}, "x", "ops1")
    assert "due_day" in exc.value.errors
    with pytest.raises(LookupError):
        svc.edit_rule("central:pf:1999-01-01", params, "x", "ops1")


def test_tax_profile_saved_and_used(repo):
    svc = service(repo)
    svc.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops1")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                    SalaryStructure({"basic": 50000, "hra": 20000, "special_allowance": 30000}),
                                    date(2026, 4, 1)), "ops1")
    new = svc.create_draft("acme", date(2026, 4, 1), user="ops1")
    assert new.slips["E1"].amount("tds") == 0  # new regime: taxable 11.25 lakh, fully rebated
    svc.update_tax_profile("acme", "E1", "ops1", regime="old", age_group="below_60", metro_city=True,
                           parents_senior=True, declarations={
                               "rent_paid": 240000, "sec_80c": 100000, "sec_80ccd_1b": 50000,
                               "sec_80d_self": 30000, "sec_80d_parents": 30000, "home_loan_interest": ""})
    stored = repo.get_employee("acme", "E1").employee
    assert stored.tax_regime == "old" and stored.metro_city and stored.parents_senior
    assert set(stored.tax_declarations) == {"rent_paid", "sec_80c", "sec_80ccd_1b", "sec_80d_self", "sec_80d_parents"}
    old = svc.create_draft("acme", date(2026, 4, 1), user="ops1")
    assert old.slips["E1"].amount("tds") == 5261  # 63,128 for the year / 12
    with pytest.raises(ServiceError) as exc:
        svc.update_tax_profile("acme", "E1", "ops1", regime="mid", age_group="x", metro_city=False,
                               parents_senior=False, declarations={"sec_80c": -1})
    assert set(exc.value.errors) == {"tax_regime", "tax_age_group", "sec_80c"}

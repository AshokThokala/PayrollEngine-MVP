from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain import Client, EmployeeRecord, FilingStatus, RunStatus
from app.engine import Employee, RuleBook, SalaryStructure
from app.services import MonthInput, PayrollService, ServiceError

RULES = RuleBook.load()
D = Decimal


def make_service(repo):
    svc = PayrollService(repo, RULES,
                         clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.add_client(Client(id="acme", legal_name="Acme Textiles", state="TG"), user="ops1")
    return svc


def hire(svc, code, components, joined=date(2026, 4, 1)):
    return svc.add_employee(
        EmployeeRecord("acme", Employee(code=code, name=code), SalaryStructure(components), joined),
        user="ops1",
    )


def staffed(repo):
    svc = make_service(repo)
    hire(svc, "E1", {"basic": 15000, "hra": 6000, "special_allowance": 4000})
    hire(svc, "E2", {"basic": 10000, "hra": 4000, "special_allowance": 4000})
    hire(svc, "E3", {"basic": 12000}, joined=date(2026, 10, 16))
    return svc


def lock_month(svc, period, inputs=None):
    run = svc.create_draft("acme", period, user="ops1", inputs=inputs)
    svc.approve(run.id, user="reviewer")
    return run, svc.lock(run.id, user="reviewer")


def test_unsupported_state_rejected(repo):
    svc = make_service(repo)
    with pytest.raises(ServiceError):
        svc.add_client(Client(id="x", legal_name="X", state="KA"), user="ops1")


def test_structure_warning_on_hire(repo):
    svc = make_service(repo)
    warnings = hire(svc, "E9", {"basic": 8000, "special_allowance": 12000})
    assert len(warnings) == 1


def test_draft_prorates_mid_month_joiner(repo):
    svc = staffed(repo)
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops1")
    assert run.id == "acme:2026-10" and run.status == RunStatus.DRAFT
    assert set(run.slips) == {"E1", "E2", "E3"}
    # E3 joined 16 Oct: 16 of 31 days
    assert run.slips["E3"].gross == D("6193.55")
    assert run.slips["E1"].net_pay == D(23000)


def test_explicit_inputs_and_unknown_employee(repo):
    svc = staffed(repo)
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops1",
                           inputs={"E1": MonthInput(paid_days=D("15.5"))})
    assert run.slips["E1"].gross == D(12500)
    with pytest.raises(ServiceError):
        svc.create_draft("acme", date(2026, 10, 1), user="ops1", inputs={"E99": MonthInput()})


def test_maker_checker_and_lock_rules(repo):
    svc = staffed(repo)
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops1")
    with pytest.raises(ServiceError, match="Maker-checker"):
        svc.approve(run.id, user="ops1")
    with pytest.raises(ServiceError):
        svc.lock(run.id, user="reviewer")  # not approved yet
    svc.approve(run.id, user="reviewer")
    svc.lock(run.id, user="reviewer")
    with pytest.raises(ServiceError, match="cannot be recalculated"):
        svc.create_draft("acme", date(2026, 10, 1), user="ops1")


def test_redrafting_replaces_a_draft(repo):
    svc = staffed(repo)
    svc.create_draft("acme", date(2026, 10, 1), user="ops1")
    run = svc.create_draft("acme", date(2026, 10, 1), user="ops1",
                           inputs={"E1": MonthInput(paid_days=D(0))})
    assert run.slips["E1"].gross == D(0)
    assert len(svc.repo.list_runs("acme")) == 1


def test_lock_schedules_filings_with_due_dates(repo):
    svc = staffed(repo)
    _, filings = lock_month(svc, date(2026, 10, 1))
    by_kind = {f.kind: f for f in filings}
    assert set(by_kind) == {"pf", "esi", "tds_deposit", "pt"}
    assert by_kind["pf"].due_on == date(2026, 11, 15)
    assert by_kind["esi"].due_on == date(2026, 11, 15)
    assert by_kind["tds_deposit"].due_on == date(2026, 11, 7)
    assert by_kind["pt"].due_on == date(2026, 11, 10)
    # PT: E1 200 + E2 150 + E3 0
    assert by_kind["pt"].amount == D(350)


def test_december_adds_lwf_and_quarterly_return(repo):
    svc = staffed(repo)
    _, filings = lock_month(svc, date(2026, 12, 1))
    by_kind = {f.kind: f for f in filings}
    assert by_kind["lwf"].due_on == date(2027, 1, 31)
    assert by_kind["lwf"].amount == D(21)  # 3 employees x (2 + 5)
    assert by_kind["form_24q"].period == "2026-27 Q3"
    assert by_kind["form_24q"].due_on == date(2027, 1, 31)


def test_march_tds_due_30_april(repo):
    svc = staffed(repo)
    _, filings = lock_month(svc, date(2027, 3, 1))
    tds = next(f for f in filings if f.kind == "tds_deposit")
    assert tds.due_on == date(2027, 4, 30)


def test_tds_uses_year_to_date_from_locked_runs(repo):
    svc = make_service(repo)
    hire(svc, "E4", {"basic": 200000})
    april, _ = lock_month(svc, date(2026, 4, 1))
    may = svc.create_draft("acme", date(2026, 5, 1), user="ops1")
    assert april.slips["E4"].amount("tds") == D(24375)
    assert may.slips["E4"].amount("tds") == D(24375)


def test_variance_flag_on_big_salary_change(repo):
    svc = staffed(repo)
    lock_month(svc, date(2026, 10, 1))
    svc.update_salary("acme", "E1", SalaryStructure({"basic": 20000, "hra": 6000, "special_allowance": 4000}), "ops1")
    run = svc.create_draft("acme", date(2026, 11, 1), user="ops1")
    assert any(f.startswith("E1: net pay changed") for f in run.flags)


def test_exited_employee_left_out_after_exit_month(repo):
    svc = staffed(repo)
    svc.exit_employee("acme", "E2", date(2026, 10, 10), "ops1")
    oct_run = svc.create_draft("acme", date(2026, 10, 1), user="ops1")
    assert oct_run.slips["E2"].gross == D("5806.45")  # 10 of 31 days
    nov_run = svc.create_draft("acme", date(2026, 11, 1), user="ops1")
    assert "E2" not in nov_run.slips


def test_filing_needs_challan_and_is_audited(repo):
    svc = staffed(repo)
    _, filings = lock_month(svc, date(2026, 10, 1))
    pf = next(f for f in filings if f.kind == "pf")
    with pytest.raises(ServiceError):
        svc.update_filing(pf.id, FilingStatus.PAID, user="ops1")
    svc.update_filing(pf.id, FilingStatus.PAID, user="ops1", challan_ref="TRRN123")
    actions = [e.action for e in svc.repo.audit_log()]
    assert actions[-4:] == ["run.draft", "run.approve", "run.lock", "filing.update"]


def test_errors_name_the_field(repo):
    svc = staffed(repo)
    with pytest.raises(ServiceError) as dup_client:
        svc.add_client(Client(id="acme", legal_name="Again", state="TG"), user="ops1")
    assert dup_client.value.field == "id"
    with pytest.raises(ServiceError) as dup_emp:
        hire(svc, "E1", {"basic": 1000})
    assert dup_emp.value.field == "code"
    assert repo.get_employee("acme", "E1").structure.components["basic"] == D(15000)  # not overwritten
    with pytest.raises(ServiceError) as early_exit:
        svc.exit_employee("acme", "E1", date(2026, 3, 1), "ops1")
    assert early_exit.value.field == "exit_on"

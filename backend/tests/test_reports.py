from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain import Client, EmployeeRecord, FilingStatus
from app.engine import Employee, SalaryStructure
from app.services import PayrollService
from app.services.reports import CATALOG, UnknownReport, run_report


def setup(repo):
    svc = PayrollService(repo, clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.ensure_rules_seeded()
    svc.add_client(Client(id="acme", legal_name="Acme", state="TG"), "ops")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi"),
                                    SalaryStructure({"basic": 15000, "hra": 6000, "special_allowance": 4000}),
                                    date(2026, 4, 1)), "ops")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E2", name="Sita"),
                                    SalaryStructure({"basic": 10000, "hra": 4000, "special_allowance": 4000}),
                                    date(2026, 4, 1)), "ops")
    for m in (9, 10):
        run = svc.create_draft("acme", date(2026, m, 1), user="ops")
        svc.approve(run.id, "rev")
        svc.lock(run.id, "rev")
    return svc


def report(repo, key, **kw):
    return run_report(repo, "acme", key, month=kw.get("month"), fy=kw.get("fy"), today=date(2026, 11, 20))


def test_catalog_keys_all_work(repo):
    setup(repo)
    for item in CATALOG:
        out = report(repo, item["key"], month=date(2026, 10, 1), fy=2026)
        assert out["title"] and isinstance(out["rows"], list)
    with pytest.raises(UnknownReport):
        report(repo, "nope")


def test_salary_register_matches_run(repo):
    setup(repo)
    out = report(repo, "salary_register", month=date(2026, 10, 1))
    run = repo.get_run("acme:2026-10")
    assert [r["code"] for r in out["rows"]] == ["E1", "E2"]
    assert out["totals"]["net"] == run.total_net
    e1 = out["rows"][0]
    assert (e1["gross"], e1["pf"], e1["pt"], e1["net"]) == (Decimal(25000), Decimal(1800), Decimal(200), Decimal(23000))
    assert out["subtitle"] == "Run status: locked"
    assert report(repo, "salary_register", month=date(2026, 12, 1))["rows"] == []


def test_statutory_summary_and_tax(repo):
    setup(repo)
    out = report(repo, "statutory_summary", fy=2026)
    assert [r["month"] for r in out["rows"]] == ["Sep 2026", "Oct 2026"]
    pf_filed = sum(f.amount for f in repo.list_filings("acme") if f.kind == "pf")
    assert out["totals"]["pf"] == pf_filed
    tax = report(repo, "tax_summary", fy=2026)
    assert [(r["code"], r["months"]) for r in tax["rows"]] == [("E1", 2), ("E2", 2)]
    assert report(repo, "tax_summary", fy=2025)["totals"]["gross"] == 0


def test_cost_trend_and_compliance(repo):
    svc = setup(repo)
    trend = report(repo, "cost_trend")
    assert [r["month"] for r in trend["rows"]] == ["Sep 2026", "Oct 2026"]
    pf = next(f for f in repo.list_filings("acme") if f.kind == "pf" and f.period == "2026-10")
    svc.update_filing(pf.id, FilingStatus.PAID, "ops", "TRRN1")
    status = report(repo, "compliance_status")
    assert status["rows"][0]["status"] == "overdue"  # September dues, due in October
    assert "1 paid" in status["subtitle"] and "overdue" in status["subtitle"]

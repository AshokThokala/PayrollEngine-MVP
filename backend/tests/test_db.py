from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.db import SqlRepository, database_from_url, make_repository, migrate
from app.domain import Client, EmployeeRecord
from app.engine import Employee, RuleBook, SalaryStructure
from app.repository import InMemoryRepository, NotFound
from app.services import PayrollService

RULES = RuleBook.load()


def sql_only(repo):
    if not isinstance(repo, SqlRepository):
        pytest.skip("SQL backends only")


def service(repo):
    svc = PayrollService(repo, RULES, clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    svc.add_client(Client(id="acme", legal_name="Acme", state="TG", pf_code="TSHYD123"), "ops1")
    svc.add_employee(EmployeeRecord("acme", Employee(code="E1", name="Ravi", esi_covered=False),
                                    SalaryStructure({"basic": 15000, "hra": 6000}),
                                    date(2026, 4, 1)), "ops1")
    return svc


def test_migrate_is_idempotent(tmp_path):
    db = database_from_url(f"sqlite:///{tmp_path / 'm.db'}")
    assert migrate(db) == ["001_initial"]
    assert migrate(db) == []


def test_make_repository_picks_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(make_repository(), InMemoryRepository)
    assert isinstance(make_repository(f"sqlite:///{tmp_path / 'x.db'}"), SqlRepository)
    with pytest.raises(ValueError):
        make_repository("mysql://nope")


def test_client_and_employee_round_trip(repo):
    svc = service(repo)
    assert repo.get_client("acme").pf_code == "TSHYD123"
    rec = repo.get_employee("acme", "E1")
    assert rec.employee.name == "Ravi" and rec.employee.esi_covered is False
    assert rec.employee.pf_member is True and rec.joined_on == date(2026, 4, 1)
    assert rec.structure.components == {"basic": Decimal(15000), "hra": Decimal(6000)}
    with pytest.raises(NotFound):
        repo.get_employee("acme", "E404")
    with pytest.raises(ValueError):
        svc.add_client(Client(id="acme", legal_name="Dup", state="TG"), "ops1")


def test_salary_history_is_versioned(repo):
    sql_only(repo)
    svc = service(repo)
    svc.update_salary("acme", "E1", SalaryStructure({"basic": 18000, "hra": 6000}), "ops1")
    repo.save_employee(repo.get_employee("acme", "E1"))  # unchanged -> no new version
    conn = repo.db.connect()
    rows = conn.cursor()
    rows.execute("SELECT version, component, amount FROM salary_components ORDER BY version, component")
    history = [(v, c, Decimal(str(a))) for v, c, a in rows.fetchall()]
    conn.close()
    assert history == [(1, "basic", Decimal(15000)), (1, "hra", Decimal(6000)),
                       (2, "basic", Decimal(18000)), (2, "hra", Decimal(6000))]
    assert repo.get_employee("acme", "E1").structure.components["basic"] == Decimal(18000)


def test_payroll_run_round_trip(repo):
    svc = service(repo)
    draft = svc.create_draft("acme", date(2026, 10, 1), user="ops1")
    loaded = repo.get_run(draft.id)
    slip, orig = loaded.slips["E1"], draft.slips["E1"]
    assert (slip.gross, slip.net_pay, slip.employer_cost) == (orig.gross, orig.net_pay, orig.employer_cost)
    assert [(l.code, l.amount, l.rule) for l in slip.deductions] == \
           [(l.code, l.amount, l.rule) for l in orig.deductions]
    assert slip.period == date(2026, 10, 31)

    svc.approve(draft.id, "reviewer")
    filings = svc.lock(draft.id, "reviewer")
    locked = repo.get_run(draft.id)
    assert locked.status.value == "locked" and locked.locked_at is not None
    assert {f.id for f in repo.list_filings("acme")} == {f.id for f in filings}
    assert repo.list_filings("other") == []


def test_audit_log_order(repo):
    service(repo)
    assert [e.action for e in repo.audit_log()] == ["client.create", "employee.create"]


def test_postgres_audit_is_append_only(repo):
    sql_only(repo)
    if repo.db.dialect != "postgres":
        pytest.skip("trigger exists on PostgreSQL only")
    service(repo)
    conn = repo.db.connect()
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM audit_events")
    conn.rollback()
    conn.close()

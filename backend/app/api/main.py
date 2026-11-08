"""FastAPI application.

Run locally:  uvicorn app.api.main:app --reload   (from backend/)

Auth is a placeholder for the MVP: the caller's name comes from the
``X-User`` header. Storage: PostgreSQL when DATABASE_URL is set, otherwise in memory.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..domain import Client, EmployeeRecord, FilingStatus, PayrollRun
from ..engine import Employee, RuleBook, SalaryStructure
from ..db import make_repository
from ..repository import NotFound
from ..services import MonthInput, PayrollService, ServiceError
from ..services.compliance import overdue
from . import errors
from . import schemas as s

app = FastAPI(title="Payroll + Compliance MVP", version="0.2.0")


@lru_cache
def get_service() -> PayrollService:
    # PostgreSQL (or SQLite) when DATABASE_URL is set, otherwise in memory.
    return PayrollService(make_repository(), RuleBook.load())


def current_user(x_user: str = Header(..., description="Placeholder auth")) -> str:
    return x_user


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse(status_code=404, content=errors.from_service(str(exc), None))


@app.exception_handler(ServiceError)
async def _rejected(_: Request, exc: ServiceError):
    return JSONResponse(status_code=409, content=errors.from_service(str(exc), exc.field))


@app.exception_handler(RequestValidationError)
async def _invalid(_: Request, exc: RequestValidationError):
    # 422 with every problem tied to its field, e.g. "PAN: This field is required".
    return JSONResponse(status_code=422, content=errors.from_validation(exc.errors()))


def _employee_out(r: EmployeeRecord) -> s.EmployeeOut:
    return s.EmployeeOut(code=r.code, name=r.employee.name, joined_on=r.joined_on,
                         exited_on=r.exited_on, components=r.structure.components,
                         monthly_total=r.structure.total)


def _lines(lines) -> list[s.LineOut]:
    return [s.LineOut(code=l.code, label=l.label, amount=l.amount, rule=l.rule) for l in lines]


def _run_out(run: PayrollRun) -> s.RunOut:
    slips = [
        s.PayslipOut(employee_code=p.employee_code, gross=p.gross,
                     total_deductions=p.total_deductions, net_pay=p.net_pay,
                     employer_cost=p.employer_cost, statutory_wages=p.statutory_wages,
                     earnings=_lines(p.earnings), deductions=_lines(p.deductions),
                     employer_contributions=_lines(p.employer_contributions),
                     warnings=p.warnings)
        for p in run.slips.values()
    ]
    return s.RunOut(id=run.id, client_id=run.client_id, period=run.period,
                    status=run.status.value, prepared_by=run.prepared_by,
                    approved_by=run.approved_by, total_gross=run.total_gross,
                    total_net=run.total_net, total_employer_cost=run.total_employer_cost,
                    flags=run.flags, slips=slips)


def _filing_out(f) -> s.FilingOut:
    return s.FilingOut(id=f.id, client_id=f.client_id, kind=f.kind, period=f.period,
                       due_on=f.due_on, status=f.status.value, amount=f.amount,
                       challan_ref=f.challan_ref)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/clients", status_code=201)
def create_client(body: s.ClientIn, user: str = Depends(current_user),
                  svc: PayrollService = Depends(get_service)):
    try:
        svc.add_client(Client(**body.model_dump()), user)
    except ServiceError:
        raise
    except ValueError as exc:  # storage-level duplicate (e.g. two requests at once)
        raise ServiceError(str(exc), field="id") from exc
    return body


@app.get("/clients")
def list_clients(svc: PayrollService = Depends(get_service)):
    return [c.__dict__ for c in svc.repo.list_clients()]


@app.post("/clients/{client_id}/employees", status_code=201, response_model=s.EmployeeCreated)
def add_employee(client_id: str, body: s.EmployeeIn, user: str = Depends(current_user),
                 svc: PayrollService = Depends(get_service)):
    flags = body.model_dump(include={"pf_member", "eps_member", "pf_on_full_wages",
                                     "esi_covered", "pt_applicable", "lwf_applicable"})
    record = EmployeeRecord(client_id, Employee(code=body.code, name=body.name, **flags),
                            SalaryStructure(body.components), body.joined_on)
    warnings = svc.add_employee(record, user)
    return s.EmployeeCreated(employee=_employee_out(record), warnings=warnings)


@app.get("/clients/{client_id}/employees", response_model=list[s.EmployeeOut])
def list_employees(client_id: str, svc: PayrollService = Depends(get_service)):
    svc.repo.get_client(client_id)
    return [_employee_out(r) for r in svc.repo.list_employees(client_id)]


@app.post("/clients/{client_id}/employees/{code}/exit", status_code=204)
def exit_employee(client_id: str, code: str, body: s.ExitIn,
                  user: str = Depends(current_user), svc: PayrollService = Depends(get_service)):
    svc.exit_employee(client_id, code, body.exit_on, user)


@app.post("/clients/{client_id}/runs", status_code=201, response_model=s.RunOut)
def create_run(client_id: str, body: s.RunIn, user: str = Depends(current_user),
               svc: PayrollService = Depends(get_service)):
    inputs = {code: MonthInput(**mi.model_dump()) for code, mi in body.inputs.items()}
    return _run_out(svc.create_draft(client_id, body.period, user, inputs))


@app.get("/clients/{client_id}/runs", response_model=list[s.RunOut])
def list_runs(client_id: str, svc: PayrollService = Depends(get_service)):
    svc.repo.get_client(client_id)
    return [_run_out(r) for r in reversed(svc.repo.list_runs(client_id))]


@app.get("/runs/{run_id}", response_model=s.RunOut)
def get_run(run_id: str, svc: PayrollService = Depends(get_service)):
    return _run_out(svc.repo.get_run(run_id))


@app.post("/runs/{run_id}/approve", response_model=s.RunOut)
def approve_run(run_id: str, user: str = Depends(current_user),
                svc: PayrollService = Depends(get_service)):
    return _run_out(svc.approve(run_id, user))


@app.post("/runs/{run_id}/lock", response_model=list[s.FilingOut])
def lock_run(run_id: str, user: str = Depends(current_user),
             svc: PayrollService = Depends(get_service)):
    return [_filing_out(f) for f in svc.lock(run_id, user)]


@app.get("/filings", response_model=list[s.FilingOut])
def list_filings(client_id: str | None = None, overdue_on: date | None = None,
                 svc: PayrollService = Depends(get_service)):
    items = svc.repo.list_filings(client_id)
    if overdue_on:
        items = overdue(items, overdue_on)
    return [_filing_out(f) for f in items]


@app.post("/filings/{filing_id}", response_model=s.FilingOut)
def update_filing(filing_id: str, body: s.FilingUpdate, user: str = Depends(current_user),
                  svc: PayrollService = Depends(get_service)):
    try:
        status = FilingStatus(body.status)
    except ValueError as exc:
        return JSONResponse(status_code=422, content=errors.from_service(
            f"Use one of: {', '.join(x.value for x in FilingStatus)}", "status"))
    return _filing_out(svc.update_filing(filing_id, status, user, body.challan_ref))

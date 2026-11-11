"""FastAPI application.

Run locally:  uvicorn app.api.main:app --reload   (from backend/)

Login: POST /auth/login returns a token; send it as "Authorization: Bearer <token>".
Roles: platform admin (all clients, rules), client admin (own client), employee (own data).
The first platform admin is created from ADMIN_EMAIL / ADMIN_PASSWORD when there are no users.
Storage: PostgreSQL when DATABASE_URL is set, otherwise in memory.
"""
from __future__ import annotations

import os
from datetime import date
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from ..domain import Client, EmployeeRecord, FilingStatus, PayrollRun, Role, User, UserStatus
from .. import rule_schemas
from ..engine import Employee, SalaryStructure
from ..db import make_repository
from ..repository import NotFound
from ..services import AccessDenied, AuthService, MonthInput, PayrollService, ServiceError
from ..services.compliance import overdue
from ..services.reports import CATALOG, UnknownReport, run_report
from . import errors
from . import schemas as s

app = FastAPI(title="ClearPay4U API", description="ClearPay4U — zero-penalty payroll", version="0.4.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)  # payslip and report responses compress well


@lru_cache
def get_service() -> PayrollService:
    # PostgreSQL (or SQLite) when DATABASE_URL is set, otherwise in memory.
    svc = PayrollService(make_repository())  # rules are read from the statutory_rules table
    svc.ensure_rules_seeded()
    return svc


@lru_cache
def get_auth() -> AuthService:
    auth = AuthService(get_service())
    auth.ensure_bootstrap_admin(os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD"))
    return auth


class NotLoggedIn(Exception):
    pass


def current_user(authorization: str | None = Header(None),
                 auth: AuthService = Depends(get_auth)) -> User:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    user = auth.user_from_token(token)
    if user is None:
        raise NotLoggedIn()
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise AccessDenied("Admins only")
    return user


def platform_admin(user: User = Depends(admin_user)) -> User:
    if not user.is_platform_admin:
        raise AccessDenied("Only the payroll service team can do this")
    return user


def employee_user(user: User = Depends(current_user)) -> User:
    if user.role != Role.EMPLOYEE:
        raise AccessDenied("Employees only")
    return user


@app.exception_handler(NotLoggedIn)
async def _not_logged_in(_: Request, exc: NotLoggedIn):
    return JSONResponse(status_code=401, content=errors.from_service("Please log in", None))


@app.exception_handler(AccessDenied)
async def _forbidden(_: Request, exc: AccessDenied):
    return JSONResponse(status_code=403, content=errors.from_service(str(exc), None))


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse(status_code=404, content=errors.from_service(str(exc), None))


@app.exception_handler(ServiceError)
async def _rejected(_: Request, exc: ServiceError):
    if exc.errors:  # several fields at once (rule validation)
        category = getattr(exc, "category", "")

        def label(key: str) -> str:
            found = rule_schemas.field_label(category, key) if category else key
            return found if found != key else errors.FIELD_LABELS.get(key, key)
        return JSONResponse(status_code=422, content=errors.from_field_errors(exc.errors, label))
    return JSONResponse(status_code=409, content=errors.from_service(str(exc), exc.field))


@app.exception_handler(RequestValidationError)
async def _invalid(_: Request, exc: RequestValidationError):
    # 422 with every problem tied to its field, e.g. "PAN: This field is required".
    return JSONResponse(status_code=422, content=errors.from_validation(exc.errors()))


def _employee_out(r: EmployeeRecord) -> s.EmployeeOut:
    e = r.employee
    return s.EmployeeOut(code=r.code, name=e.name, joined_on=r.joined_on,
                         exited_on=r.exited_on, components=r.structure.components,
                         monthly_total=r.structure.total,
                         flags={k: getattr(e, k) for k in PayrollService.EMPLOYEE_FLAGS},
                         tax=s.TaxProfile(tax_regime=e.tax_regime, tax_age_group=e.tax_age_group,
                                          metro_city=e.metro_city, parents_senior=e.parents_senior,
                                          declarations=e.tax_declarations))


def _lines(lines) -> list[s.LineOut]:
    return [s.LineOut(code=l.code, label=l.label, amount=l.amount, rule=l.rule) for l in lines]


def _payslip_out(p) -> s.PayslipOut:
    return s.PayslipOut(employee_code=p.employee_code, gross=p.gross,
                        total_deductions=p.total_deductions, net_pay=p.net_pay,
                        employer_cost=p.employer_cost, statutory_wages=p.statutory_wages,
                        earnings=_lines(p.earnings), deductions=_lines(p.deductions),
                        employer_contributions=_lines(p.employer_contributions),
                        warnings=p.warnings)


def _run_out(run: PayrollRun) -> s.RunOut:
    slips = [_payslip_out(p) for p in run.slips.values()]
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
    """Liveness for load balancers: the process is up (does not touch the database)."""
    return {"status": "ok"}


@app.post("/clients", status_code=201)
def create_client(body: s.ClientIn, user: User = Depends(platform_admin),
                  svc: PayrollService = Depends(get_service)):
    try:
        svc.add_client(Client(**body.model_dump()), user.email)
    except ServiceError:
        raise
    except ValueError as exc:  # storage-level duplicate (e.g. two requests at once)
        raise ServiceError(str(exc), field="id") from exc
    return body


@app.put("/clients/{client_id}")
def update_client(client_id: str, body: s.ClientUpdate, actor: User = Depends(admin_user),
                  svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    """Edit a client's details. ID and state are fixed."""
    auth.check_client(actor, client_id)
    return svc.update_client(client_id, body.model_dump(exclude_none=True), actor.email).__dict__


@app.get("/clients")
def list_clients(user: User = Depends(admin_user), svc: PayrollService = Depends(get_service)):
    return [c.__dict__ for c in svc.repo.list_clients() if user.can_manage(c.id)]


@app.post("/clients/{client_id}/employees", status_code=201, response_model=s.EmployeeCreated)
def add_employee(client_id: str, body: s.EmployeeIn, actor: User = Depends(admin_user),
                 svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    user = actor.email
    flags = body.model_dump(include={"pf_member", "eps_member", "pf_on_full_wages",
                                     "esi_covered", "pt_applicable", "lwf_applicable"})
    record = EmployeeRecord(client_id, Employee(code=body.code, name=body.name, **flags),
                            SalaryStructure(body.components), body.joined_on)
    warnings = svc.add_employee(record, user)
    if body.tax:
        record = svc.update_tax_profile(client_id, body.code, user, regime=body.tax.tax_regime,
                                        age_group=body.tax.tax_age_group,
                                        metro_city=body.tax.metro_city,
                                        parents_senior=body.tax.parents_senior,
                                        declarations=body.tax.declarations)
    return s.EmployeeCreated(employee=_employee_out(record), warnings=warnings)


@app.get("/clients/{client_id}/employees", response_model=list[s.EmployeeOut])
def list_employees(client_id: str, actor: User = Depends(admin_user),
                   svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    svc.repo.get_client(client_id)
    return [_employee_out(r) for r in svc.repo.list_employees(client_id)]


@app.put("/clients/{client_id}/employees/{code}", response_model=s.EmployeeCreated)
def update_employee(client_id: str, code: str, body: s.EmployeeUpdate, actor: User = Depends(admin_user),
                    svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    """Edit name, statutory settings and salary (a salary change is kept as a new version)."""
    auth.check_client(actor, client_id)
    warnings = svc.update_employee(client_id, code, actor.email, name=body.name,
                                   components=body.components, flags=body.flags)
    return s.EmployeeCreated(employee=_employee_out(svc.repo.get_employee(client_id, code)), warnings=warnings)


@app.post("/clients/{client_id}/employees/{code}/view-as", response_model=s.LoginOut)
def view_as_employee(client_id: str, code: str, actor: User = Depends(admin_user),
                     auth: AuthService = Depends(get_auth)):
    """A one-hour, read-only session showing the employee portal as this employee sees it."""
    viewer, token = auth.view_as(actor, client_id, code)
    return s.LoginOut(token=token, user=_user_out(viewer))


@app.put("/clients/{client_id}/employees/{code}/tax", response_model=s.EmployeeOut)
def update_tax_profile(client_id: str, code: str, body: s.TaxProfile,
                       actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service),
                       auth: AuthService = Depends(get_auth)):
    """Regime choice and old-regime declarations used for monthly TDS."""
    auth.check_client(actor, client_id)
    record = svc.update_tax_profile(client_id, code, actor.email, regime=body.tax_regime,
                                    age_group=body.tax_age_group, metro_city=body.metro_city,
                                    parents_senior=body.parents_senior,
                                    declarations=body.declarations)
    return _employee_out(record)


@app.post("/clients/{client_id}/employees/{code}/exit", status_code=204)
def exit_employee(client_id: str, code: str, body: s.ExitIn,
                  actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service),
                  auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    svc.exit_employee(client_id, code, body.exit_on, actor.email)


@app.post("/clients/{client_id}/runs", status_code=201, response_model=s.RunOut)
def create_run(client_id: str, body: s.RunIn, actor: User = Depends(admin_user),
               svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    inputs = {code: MonthInput(**mi.model_dump()) for code, mi in body.inputs.items()}
    return _run_out(svc.create_draft(client_id, body.period, actor.email, inputs))


@app.get("/clients/{client_id}/runs", response_model=list[s.RunSummaryOut])
def list_runs(client_id: str, actor: User = Depends(admin_user),
              svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    """Run headers and totals, newest first. Fetch /runs/{id} for the payslips."""
    auth.check_client(actor, client_id)
    svc.repo.get_client(client_id)
    return [s.RunSummaryOut(id=r.id, client_id=r.client_id, period=r.period, status=r.status.value,
                            prepared_by=r.prepared_by, approved_by=r.approved_by,
                            employees=r.employees, total_gross=r.total_gross, total_net=r.total_net,
                            total_employer_cost=r.total_employer_cost)
            for r in svc.repo.list_run_summaries(client_id)]


@app.get("/runs/{run_id}", response_model=s.RunOut)
def get_run(run_id: str, actor: User = Depends(admin_user),
            svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    run = svc.repo.get_run(run_id)
    auth.check_client(actor, run.client_id)
    return _run_out(run)


@app.post("/runs/{run_id}/approve", response_model=s.RunOut)
def approve_run(run_id: str, actor: User = Depends(admin_user),
                svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, svc.repo.get_run(run_id).client_id)
    return _run_out(svc.approve(run_id, actor.email))


@app.post("/runs/{run_id}/lock", response_model=list[s.FilingOut])
def lock_run(run_id: str, actor: User = Depends(admin_user),
             svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, svc.repo.get_run(run_id).client_id)
    return [_filing_out(f) for f in svc.lock(run_id, actor.email)]


@app.get("/filings", response_model=list[s.FilingOut])
def list_filings(client_id: str | None = None, overdue_on: date | None = None,
                 limit: int = Query(500, ge=1, le=2000), offset: int = Query(0, ge=0),
                 actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service)):
    if not actor.is_platform_admin:
        client_id = actor.client_id  # client admins only ever see their own filings
    items = svc.repo.list_filings(client_id)
    if overdue_on:
        items = overdue(items, overdue_on)
    return [_filing_out(f) for f in items[offset:offset + limit]]


@app.post("/filings/{filing_id}", response_model=s.FilingOut)
def update_filing(filing_id: str, body: s.FilingUpdate, actor: User = Depends(admin_user),
                  svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, svc.repo.get_filing(filing_id).client_id)
    user = actor.email
    try:
        status = FilingStatus(body.status)
    except ValueError as exc:
        return JSONResponse(status_code=422, content=errors.from_service(
            f"Use one of: {', '.join(x.value for x in FilingStatus)}", "status"))
    return _filing_out(svc.update_filing(filing_id, status, user, body.challan_ref))


# --- compliance rules ----------------------------------------------------------

def _rule_out(r) -> s.RuleOut:
    return s.RuleOut(id=r.id, scope=r.scope, category=r.category,
                     category_label=rule_schemas.CATEGORIES.get(r.category, {}).get("label", r.category),
                     valid_from=r.valid_from, valid_to=r.valid_to, params=r.params, source=r.source,
                     created_by=r.created_by, created_at=r.created_at)


@app.get("/rules/categories")
def rule_categories():
    """Rule types and their fields - the UI builds the Add rule form from this."""
    return [{"category": k, **v} for k, v in rule_schemas.CATEGORIES.items()]


@app.get("/rules/states")
def rule_states(svc: PayrollService = Depends(get_service)):
    """All states, flagging those with at least one rule (clients can be created there)."""
    supported = set(svc.rules.supported_states)
    return [{"code": code, "name": name, "supported": code in supported}
            for code, name in sorted(rule_schemas.STATE_NAMES.items(), key=lambda kv: kv[1])]


@app.get("/rules", response_model=list[s.RuleOut])
def list_rules(scope: str | None = None, category: str | None = None,
               actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service)):
    return [_rule_out(r) for r in svc.repo.list_rules()
            if scope in (None, r.scope) and category in (None, r.category)]


@app.post("/rules", status_code=201, response_model=s.RuleCreated)
def create_rule(body: s.RuleIn, actor: User = Depends(platform_admin),
                svc: PayrollService = Depends(get_service)):
    try:
        rule, closed = svc.add_rule(body.scope, body.category, body.valid_from, body.params,
                                    body.source, actor.email)
    except ServiceError as exc:
        exc.category = body.category
        raise
    return s.RuleCreated(rule=_rule_out(rule), closed=_rule_out(closed) if closed else None)


@app.put("/rules/{rule_id}", response_model=s.RuleOut)
def edit_rule(rule_id: str, body: s.RuleEdit, actor: User = Depends(platform_admin),
              svc: PayrollService = Depends(get_service)):
    """Correct the values or source of an existing version. Dates do not change."""
    category = rule_id.split(":")[1] if rule_id.count(":") == 2 else ""
    try:
        rule = svc.edit_rule(rule_id, body.params, body.source, actor.email)
    except LookupError as exc:
        raise NotFound(str(exc)) from exc
    except ServiceError as exc:
        exc.category = category
        raise
    return _rule_out(rule)


# --- login and sign-up ---------------------------------------------------------------

def _user_out(u: User) -> s.UserOut:
    return s.UserOut(id=u.id, email=u.email, name=u.name, role=u.role.value, status=u.status.value,
                     client_id=u.client_id, employee_code=u.employee_code,
                     is_platform_admin=u.is_platform_admin, impersonated_by=u.impersonated_by)


@app.post("/auth/login", response_model=s.LoginOut)
def login(body: s.LoginIn, auth: AuthService = Depends(get_auth)):
    user, token = auth.login(body.email, body.password)
    return s.LoginOut(token=token, user=_user_out(user))


@app.post("/auth/signup/client", status_code=201, response_model=s.LoginOut)
def signup_client(body: s.ClientSignupIn, auth: AuthService = Depends(get_auth)):
    """A business signs up: creates the client and its admin login, then logs in."""
    auth.signup_client(Client(**body.client.model_dump()), body.name, body.email, body.password)
    user, token = auth.login(body.email, body.password)
    return s.LoginOut(token=token, user=_user_out(user))


@app.post("/auth/signup/employee", status_code=201, response_model=s.UserOut)
def signup_employee(body: s.EmployeeSignupIn, auth: AuthService = Depends(get_auth)):
    """An employee signs up; they can log in once their employer approves the account."""
    return _user_out(auth.signup_employee(body.client_id, body.employee_code, body.name,
                                          body.email, body.password))


@app.get("/auth/me", response_model=s.UserOut)
def me(user: User = Depends(current_user)):
    return _user_out(user)


# --- user management (admins) -------------------------------------------------------------

@app.get("/users", response_model=list[s.UserOut])
def list_users(client_id: str | None = None, limit: int = Query(500, ge=1, le=2000),
               offset: int = Query(0, ge=0), actor: User = Depends(admin_user),
               auth: AuthService = Depends(get_auth)):
    return [_user_out(u) for u in auth.list_users(actor, client_id)[offset:offset + limit]]


@app.post("/users/{user_id}/{action}", response_model=s.UserOut)
def change_user(user_id: str, action: str, actor: User = Depends(admin_user),
                auth: AuthService = Depends(get_auth)):
    status = {"approve": UserStatus.ACTIVE, "enable": UserStatus.ACTIVE,
              "disable": UserStatus.DISABLED}.get(action)
    if status is None:
        raise NotFound(f"Unknown action {action!r}")
    return _user_out(auth.set_status(actor, user_id, status))


# --- employee self-service --------------------------------------------------------------

@app.get("/me/employee", response_model=s.MeOut)
def my_employee(user: User = Depends(employee_user), auth: AuthService = Depends(get_auth)):
    client, record = auth.my_record(user)
    return s.MeOut(client_id=client.id, client_name=client.legal_name, employee=_employee_out(record))


@app.get("/me/payslips", response_model=list[s.MyPayslipOut])
def my_payslips(user: User = Depends(employee_user), auth: AuthService = Depends(get_auth)):
    return [s.MyPayslipOut(run_id=run_id, period=period, payslip=_payslip_out(slip))
            for run_id, period, slip in auth.my_payslips(user)]


@app.put("/me/tax", response_model=s.EmployeeOut)
def update_my_tax(body: s.TaxProfile, user: User = Depends(employee_user),
                  auth: AuthService = Depends(get_auth)):
    record = auth.update_my_tax(user, regime=body.tax_regime, age_group=body.tax_age_group,
                                metro_city=body.metro_city, parents_senior=body.parents_senior,
                                declarations=body.declarations)
    return _employee_out(record)


# --- reports -----------------------------------------------------------------------------

@app.get("/reports")
def report_catalog(actor: User = Depends(admin_user)):
    return CATALOG


@app.get("/clients/{client_id}/reports/{key}")
def get_report(client_id: str, key: str, month: date | None = None, fy: int | None = Query(None, ge=2000, le=2100),
               actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service),
               auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    svc.repo.get_client(client_id)
    try:
        return run_report(svc.repo, client_id, key, month=month, fy=fy, today=svc.clock().date())
    except UnknownReport as exc:
        raise NotFound(str(exc)) from exc

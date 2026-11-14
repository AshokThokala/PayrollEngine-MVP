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
from ..services.billing import PLANS, BillingService
from ..services.onboarding import all_clients, client_checklist
from ..services.employee_onboarding import EmployeeOnboardingService
from ..mailer import SmtpMailer, app_url
from ..services import tax as tax_rules
from ..services.search import search as run_search
from ..services.paycodes import CALC_LABELS as PAY_CALC_LABELS, TAX_LABELS as PAY_TAX_LABELS, PayCodeService, client_pay_codes
from ..services.timesheets import TimeService
from ..services.deductions import CALC_LABELS, TAX_SECTIONS, DeductionService, client_types
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


def get_billing(svc: PayrollService = Depends(get_service)) -> BillingService:
    return BillingService(svc)


@lru_cache
def get_mailer():
    return SmtpMailer()


def get_employee_onboarding(request: Request, auth: AuthService = Depends(get_auth),
                            mailer=Depends(get_mailer)) -> EmployeeOnboardingService:
    # Links in emails use APP_URL, or else the address the browser is using (Origin header).
    base = app_url() or request.headers.get("origin", "")
    return EmployeeOnboardingService(auth, mailer, base)


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
                         monthly_total=r.structure.total, pay_type=e.pay_type, hourly_rate=e.hourly_rate,
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
    record = EmployeeRecord(client_id, Employee(code=body.code, name=body.name, **flags, pay_type=body.pay_type,
                                                hourly_rate=body.hourly_rate or 0),
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
                                   components=body.components, flags=body.flags,
                                   pay_type=body.pay_type, hourly_rate=body.hourly_rate)
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


@app.post("/users", status_code=201, response_model=s.UserOut)
def add_user(body: s.UserIn, actor: User = Depends(admin_user), auth: AuthService = Depends(get_auth)):
    """Add an admin login (active straight away). Employees join through invites instead."""
    return _user_out(auth.create_admin(actor, name=body.name, email=body.email, password=body.password,
                                       client_id=body.client_id))


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


# --- client onboarding ---------------------------------------------------------------------

@app.get("/onboarding/clients")
def onboarding_overview(actor: User = Depends(platform_admin), svc: PayrollService = Depends(get_service)):
    """Every client's onboarding progress, least complete first."""
    return all_clients(svc)


@app.get("/clients/{client_id}/onboarding")
def onboarding_checklist(client_id: str, actor: User = Depends(admin_user),
                         svc: PayrollService = Depends(get_service), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    return client_checklist(svc, client_id)


# --- billing --------------------------------------------------------------------------------

def _plan_out(p):
    return None if p is None else {
        "plan": p.plan, "label": PLANS[p.plan]["label"], "rate_per_employee": p.rate_per_employee,
        "minimum_fee": p.minimum_fee, "onboarding_fee": p.onboarding_fee, "gst_rate": p.gst_rate,
        "billing_email": p.billing_email, "starts_on": p.starts_on}


def _invoice_out(i):
    return {"id": i.id, "client_id": i.client_id, "number": i.number, "period": i.period,
            "status": i.status.value, "lines": i.lines, "subtotal": i.subtotal, "cgst": i.cgst,
            "sgst": i.sgst, "igst": i.igst, "total": i.total, "issue_date": i.issue_date,
            "due_date": i.due_date, "paid_on": i.paid_on, "payment_ref": i.payment_ref}


@app.get("/billing/plans")
def billing_plans(actor: User = Depends(admin_user)):
    return [{"plan": k, **v} for k, v in PLANS.items()]


@app.get("/billing/overview")
def billing_overview(actor: User = Depends(platform_admin), billing: BillingService = Depends(get_billing),
                     svc: PayrollService = Depends(get_service)):
    return billing.overview(svc.clock().date())


@app.get("/clients/{client_id}/billing")
def client_billing(client_id: str, actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service),
                   auth: AuthService = Depends(get_auth)):
    """Plan and invoices. Client admins see issued, paid and void invoices; drafts are internal."""
    auth.check_client(actor, client_id)
    client = svc.repo.get_client(client_id)
    invoices = [i for i in svc.repo.list_invoices(client_id)
                if actor.is_platform_admin or i.status.value != "draft"]
    return {"client": client.__dict__, "plan": _plan_out(svc.repo.get_billing_plan(client_id)),
            "invoices": [_invoice_out(i) for i in invoices]}


@app.put("/clients/{client_id}/billing/plan")
def set_billing_plan(client_id: str, body: s.PlanIn, actor: User = Depends(platform_admin),
                     billing: BillingService = Depends(get_billing)):
    return _plan_out(billing.set_plan(client_id, actor.email, **body.model_dump()))


@app.post("/clients/{client_id}/invoices", status_code=201)
def generate_invoice(client_id: str, body: s.InvoiceIn, actor: User = Depends(platform_admin),
                     billing: BillingService = Depends(get_billing)):
    return _invoice_out(billing.generate(client_id, body.month, actor.email))


@app.post("/invoices/{invoice_id}/{action}")
def invoice_action(invoice_id: str, action: str, body: s.InvoicePayment | None = None,
                   actor: User = Depends(platform_admin), billing: BillingService = Depends(get_billing)):
    if action == "issue":
        return _invoice_out(billing.issue(invoice_id, actor.email))
    if action == "void":
        return _invoice_out(billing.void(invoice_id, actor.email))
    if action == "pay":
        if body is None:
            raise ServiceError("Enter the payment date and reference", field="reference")
        return _invoice_out(billing.mark_paid(invoice_id, actor.email, body.paid_on, body.reference))
    raise NotFound(f"Unknown action {action!r}")


# --- employee invites, registration and onboarding --------------------------------------------

@app.post("/clients/{client_id}/employees/{code}/invite", status_code=201)
def invite_employee(client_id: str, code: str, body: s.InviteIn, actor: User = Depends(admin_user),
                    eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    """Make a one-time registration link and email it. The token is shown once; only its hash is stored."""
    invite, token, delivery = eo.invite(actor, client_id, code, body.email)
    return {"invite_id": invite.id, "email": invite.email, "expires_at": invite.expires_at,
            "path": f"/invite/{token}", "email_sent": delivery["sent"], "email_error": delivery["error"]}


@app.post("/invites/{invite_id}/revoke")
def revoke_invite(invite_id: str, actor: User = Depends(admin_user),
                  eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    eo.revoke(actor, invite_id)
    return {"ok": True}


@app.get("/invite/{token}")
def invite_details(token: str, eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    """Public: what the registration page shows for a valid link."""
    return eo.lookup(token)


@app.post("/invite/{token}/accept", status_code=201, response_model=s.LoginOut)
def accept_invite(token: str, body: s.InviteAcceptIn, auth: AuthService = Depends(get_auth),
                  eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    """Public: the employee sets their name and password, and is logged in."""
    user = eo.accept(token, body.name, body.password)
    user, session_token = auth.login(user.email, body.password)
    return s.LoginOut(token=session_token, user=_user_out(user))


@app.get("/clients/{client_id}/employee-onboarding")
def employee_onboarding_list(client_id: str, actor: User = Depends(admin_user),
                             eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    return eo.status_list(actor, client_id)


@app.get("/clients/{client_id}/employees/{code}/profile")
def employee_profile(client_id: str, code: str, actor: User = Depends(admin_user),
                     eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    return eo.profile_for_admin(actor, client_id, code)


@app.post("/clients/{client_id}/employees/{code}/profile/{decision}")
def review_profile(client_id: str, code: str, decision: str, body: s.ReviewIn | None = None,
                   actor: User = Depends(admin_user),
                   eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    if decision not in ("verify", "return"):
        raise NotFound(f"Unknown decision {decision!r}")
    return eo.review(actor, client_id, code, approve=decision == "verify", note=(body.note if body else ""))


@app.get("/me/onboarding")
def my_onboarding(user: User = Depends(employee_user),
                  eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    return eo.my_profile(user)


@app.put("/me/onboarding")
def save_my_onboarding(body: s.ProfileIn, user: User = Depends(employee_user),
                       eo: EmployeeOnboardingService = Depends(get_employee_onboarding)):
    data = body.model_dump()
    submit = data.pop("submit")
    return eo.save_my_profile(user, data, submit=submit)

# --- income tax rules page -------------------------------------------------------------------

@app.get("/tax/rules")
def tax_rules_overview(on: date | None = None, actor: User = Depends(admin_user),
                       svc: PayrollService = Depends(get_service)):
    """Both regimes' slabs, deductions and limits in force on a date, TDS due dates and version history."""
    return tax_rules.overview(svc, on or svc.clock().date())


@app.post("/tax/calculate")
def tax_calculate(body: s.TaxCalcIn, actor: User = Depends(current_user),
                  svc: PayrollService = Depends(get_service)):
    """Tax for a yearly salary under both regimes, step by step."""
    data = body.model_dump()
    on = data.pop("on") or svc.clock().date()
    return tax_rules.calculate(svc, on, data)


# --- search (main screen) ----------------------------------------------------------------------

@app.get("/search")
def search(q: str = "", actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service)):
    """Employees (by name or code) the user can see."""
    return run_search(svc, actor, q)


# --- deduction master and employee deductions ----------------------------------------------------

def get_deductions(svc: PayrollService = Depends(get_service)) -> DeductionService:
    return DeductionService(svc)


def _dtype_out(t):
    return {"code": t.code, "name": t.name, "category": t.category.value, "calc": t.calc.value,
            "calc_label": CALC_LABELS[t.calc.value], "payslip_label": t.payslip_label,
            "default_value": t.default_value, "max_amount": t.max_amount, "tax_section": t.tax_section,
            "description": t.description, "active": t.active, "system": t.system}


def _ededuct_out(d, types, names=None):
    t = types.get(d.deduction_code)
    out = {"id": d.id, "employee_code": d.employee_code, "deduction_code": d.deduction_code,
           "name": t.name if t else d.deduction_code, "calc": t.calc.value if t else "fixed",
           "value": d.value, "start_month": d.start_month, "end_month": d.end_month, "note": d.note}
    if names is not None:
        out["employee_name"] = names.get(d.employee_code, d.employee_code)
    return out


@app.get("/deduction-types")
def deduction_types(actor: User = Depends(admin_user), ds: DeductionService = Depends(get_deductions)):
    """The master list of deductions an employee can have, with the choices for the form."""
    return {"types": [_dtype_out(t) for t in ds.types()], "calcs": CALC_LABELS, "tax_sections": TAX_SECTIONS}


@app.post("/deduction-types", status_code=201)
def add_deduction_type(body: s.DeductionTypeIn, actor: User = Depends(platform_admin),
                       ds: DeductionService = Depends(get_deductions)):
    return _dtype_out(ds.save_type(actor, body.model_dump()))


@app.put("/deduction-types/{code}")
def edit_deduction_type(code: str, body: s.DeductionTypeIn, actor: User = Depends(platform_admin),
                        ds: DeductionService = Depends(get_deductions)):
    return _dtype_out(ds.save_type(actor, body.model_dump(), code=code))


@app.get("/clients/{client_id}/deductions")
def client_deductions(client_id: str, actor: User = Depends(admin_user), ds: DeductionService = Depends(get_deductions),
                      auth: AuthService = Depends(get_auth)):
    """Every master deduction with this client's choice (on/off, own default, cap, payslip name)."""
    auth.check_client(actor, client_id)
    rows = []
    for r in ds.client_settings(client_id):
        t = r["type"]
        rows.append({**_dtype_out(t), "statutory": r["statutory"], "enabled": r["enabled"],
                     "master_default_value": t.default_value, "master_max_amount": t.max_amount,
                     "master_payslip_label": t.payslip_label, "default_value": r["default_value"],
                     "max_amount": r["max_amount"], "payslip_label": r["payslip_label"], "employees": r["employees"]})
    return rows


@app.put("/clients/{client_id}/deductions/{code}")
def set_client_deduction(client_id: str, code: str, body: s.ClientDeductionIn, actor: User = Depends(admin_user),
                         ds: DeductionService = Depends(get_deductions), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    cd = ds.set_client(actor, client_id, code, body.model_dump())
    return {"code": cd.deduction_code, "enabled": cd.enabled, "default_value": cd.default_value,
            "max_amount": cd.max_amount, "payslip_label": cd.payslip_label}


@app.get("/clients/{client_id}/deductions/available")
def available_deductions(client_id: str, actor: User = Depends(admin_user), svc: PayrollService = Depends(get_service),
                         auth: AuthService = Depends(get_auth)):
    """Deductions this client's employees can be given (switched on, with the client's defaults)."""
    auth.check_client(actor, client_id)
    return [_dtype_out(t) for t in client_types(svc.repo, client_id).values()]


@app.get("/clients/{client_id}/employee-deductions")
def all_employee_deductions(client_id: str, actor: User = Depends(admin_user),
                            ds: DeductionService = Depends(get_deductions), svc: PayrollService = Depends(get_service),
                            auth: AuthService = Depends(get_auth)):
    """Every employee's standing deductions for the client."""
    auth.check_client(actor, client_id)
    types = {t.code: t for t in ds.types()}
    names = {r.code: r.employee.name for r in svc.repo.list_employees(client_id)}
    return [_ededuct_out(d, types, names) for d in ds.for_client(client_id)]


@app.get("/clients/{client_id}/employees/{code}/deductions")
def employee_deductions(client_id: str, code: str, actor: User = Depends(admin_user),
                        ds: DeductionService = Depends(get_deductions), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    types = {t.code: t for t in ds.types()}
    return [_ededuct_out(d, types) for d in ds.for_employee(client_id, code)]


@app.post("/clients/{client_id}/employees/{code}/deductions", status_code=201)
def add_employee_deduction(client_id: str, code: str, body: s.EmployeeDeductionIn,
                           actor: User = Depends(admin_user), ds: DeductionService = Depends(get_deductions),
                           auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    d = ds.save_for_employee(actor, client_id, code, body.model_dump())
    return _ededuct_out(d, {t.code: t for t in ds.types()})


@app.put("/clients/{client_id}/employees/{code}/deductions/{deduction_id}")
def edit_employee_deduction(client_id: str, code: str, deduction_id: str, body: s.EmployeeDeductionIn,
                            actor: User = Depends(admin_user), ds: DeductionService = Depends(get_deductions),
                            auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    d = ds.save_for_employee(actor, client_id, code, body.model_dump(), deduction_id=deduction_id)
    return _ededuct_out(d, {t.code: t for t in ds.types()})


@app.delete("/clients/{client_id}/employees/{code}/deductions/{deduction_id}")
def delete_employee_deduction(client_id: str, code: str, deduction_id: str, actor: User = Depends(admin_user),
                              ds: DeductionService = Depends(get_deductions),
                              auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    ds.delete_for_employee(actor, client_id, code, deduction_id)
    return {"ok": True}


# --- pay codes (earnings): master, client, employee ------------------------------------------

def get_paycodes(svc: PayrollService = Depends(get_service)) -> PayCodeService:
    return PayCodeService(svc)


def _paycode_out(p, wages: set[str]):
    return {"code": p.code, "name": p.name, "kind": p.kind.value, "tax": p.tax.value, "tax_label": PAY_TAX_LABELS[p.tax.value],
            "calc": p.calc, "calc_label": PAY_CALC_LABELS[p.calc], "default_value": p.default_value,
            "payslip_label": p.payslip_label, "tax_section": p.tax_section, "description": p.description,
            "core": p.core, "active": p.active, "system": p.system, "in_wages": p.code in wages}


@app.get("/pay-codes")
def pay_codes(actor: User = Depends(admin_user), pc: PayCodeService = Depends(get_paycodes)):
    wages = pc.wage_codes()
    return {"codes": [_paycode_out(p, wages) for p in pc.codes()], "tax": PAY_TAX_LABELS, "calcs": PAY_CALC_LABELS}


@app.post("/pay-codes", status_code=201)
def add_pay_code(body: s.PayCodeIn, actor: User = Depends(platform_admin), pc: PayCodeService = Depends(get_paycodes)):
    return _paycode_out(pc.save_code(actor, body.model_dump()), pc.wage_codes())


@app.put("/pay-codes/{code}")
def edit_pay_code(code: str, body: s.PayCodeIn, actor: User = Depends(platform_admin),
                  pc: PayCodeService = Depends(get_paycodes)):
    return _paycode_out(pc.save_code(actor, body.model_dump(), code=code), pc.wage_codes())


@app.get("/clients/{client_id}/pay-codes")
def client_pay_code_settings(client_id: str, actor: User = Depends(admin_user), pc: PayCodeService = Depends(get_paycodes),
                             auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    wages = pc.wage_codes()
    return [{**_paycode_out(r["code"], wages), "enabled": r["enabled"], "master_default_value": r["code"].default_value,
             "master_payslip_label": r["code"].payslip_label, "default_value": r["default_value"],
             "payslip_label": r["payslip_label"], "employees": r["employees"], "locked": r["locked"]}
            for r in pc.client_settings(client_id)]


@app.put("/clients/{client_id}/pay-codes/{code}")
def set_client_pay_code(client_id: str, code: str, body: s.ClientPayCodeIn, actor: User = Depends(admin_user),
                        pc: PayCodeService = Depends(get_paycodes), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    cp = pc.set_client(actor, client_id, code, body.model_dump())
    return {"code": cp.pay_code, "enabled": cp.enabled, "default_value": cp.default_value, "payslip_label": cp.payslip_label}


@app.get("/clients/{client_id}/pay-codes/available")
def available_pay_codes(client_id: str, actor: User = Depends(admin_user), pc: PayCodeService = Depends(get_paycodes),
                        auth: AuthService = Depends(get_auth)):
    """Pay codes this client's employees can get (salary and variable), with the client's defaults and names."""
    auth.check_client(actor, client_id)
    wages = pc.wage_codes()
    return [_paycode_out(p, wages) for p in client_pay_codes(pc.repo, client_id).values()]


@app.get("/clients/{client_id}/employee-pay")
def employee_pay_grid(client_id: str, include_exited: bool = False, actor: User = Depends(admin_user),
                      pc: PayCodeService = Depends(get_paycodes), auth: AuthService = Depends(get_auth)):
    """Every employee's monthly salary by pay code."""
    auth.check_client(actor, client_id)
    wages = pc.wage_codes()
    grid = pc.employee_grid(client_id, include_exited)
    return {"pay_codes": [_paycode_out(p, wages) for p in grid["pay_codes"]], "employees": grid["employees"]}


@app.put("/clients/{client_id}/employees/{code}/pay")
def set_employee_pay(client_id: str, code: str, body: s.EmployeePayIn, actor: User = Depends(admin_user),
                     pc: PayCodeService = Depends(get_paycodes), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    return {"warnings": pc.set_employee_pay(actor, client_id, code, body.components)}


# --- time entry ----------------------------------------------------------------------------------

def get_time(svc: PayrollService = Depends(get_service)) -> TimeService:
    return TimeService(svc)


@app.get("/clients/{client_id}/time/{month}")
def time_month(client_id: str, month: str, actor: User = Depends(admin_user), ts: TimeService = Depends(get_time),
               auth: AuthService = Depends(get_auth)):
    """Every active employee's time for the month (YYYY-MM), with totals and overtime pay."""
    auth.check_client(actor, client_id)
    return ts.month_view(client_id, month)


@app.put("/clients/{client_id}/employees/{code}/time/{month}")
def save_time(client_id: str, code: str, month: str, body: s.TimesheetIn, actor: User = Depends(admin_user),
              ts: TimeService = Depends(get_time), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    t = ts.save(actor, client_id, code, month, body.days, body.note, body.approve)
    return {"employee_code": t.employee_code, "month": t.month, "status": t.status.value}


@app.post("/clients/{client_id}/time/{month}/approve")
def approve_time(client_id: str, month: str, body: s.TimeApproveIn, actor: User = Depends(admin_user),
                 ts: TimeService = Depends(get_time), auth: AuthService = Depends(get_auth)):
    auth.check_client(actor, client_id)
    return {"changed": ts.approve(actor, client_id, month, body.codes, body.approve)}

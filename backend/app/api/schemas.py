"""Request and response models for the HTTP API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, Field

Amount = Annotated[Decimal, Field(ge=0)]
RequiredText = Annotated[str, Field(min_length=1)]


class ClientIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    legal_name: RequiredText
    state: str = "TG"
    pan: str = ""
    tan: str = ""
    pf_code: str = ""
    esi_code: str = ""
    pt_registration: str = ""


class TaxProfile(BaseModel):
    tax_regime: str = "new"
    tax_age_group: str = "below_60"
    metro_city: bool = False
    parents_senior: bool = False
    declarations: dict[str, Decimal | str | None] = {}


class EmployeeIn(BaseModel):
    code: RequiredText
    name: RequiredText
    joined_on: date
    components: dict[str, Amount] = Field(min_length=1)
    pf_member: bool = True
    eps_member: bool = True
    pf_on_full_wages: bool = False
    esi_covered: bool | None = None
    pt_applicable: bool = True
    lwf_applicable: bool = True
    tax: TaxProfile | None = None


class EmployeeOut(BaseModel):
    code: str
    name: str
    joined_on: date
    exited_on: date | None
    components: dict[str, Decimal]
    monthly_total: Decimal
    flags: dict[str, bool | None] = {}
    tax: TaxProfile


class EmployeeCreated(BaseModel):
    employee: EmployeeOut
    warnings: list[str]


class ExitIn(BaseModel):
    exit_on: date


class MonthInputIn(BaseModel):
    paid_days: Amount | None = None
    overtime: Amount = Decimal(0)
    other_earnings: dict[str, Amount] = {}
    other_deductions: dict[str, Amount] = {}


class RunIn(BaseModel):
    period: date
    inputs: dict[str, MonthInputIn] = {}


class LineOut(BaseModel):
    code: str
    label: str
    amount: Decimal
    rule: str | None


class PayslipOut(BaseModel):
    employee_code: str
    gross: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    employer_cost: Decimal
    statutory_wages: Decimal
    earnings: list[LineOut]
    deductions: list[LineOut]
    employer_contributions: list[LineOut]
    warnings: list[str]


class RunOut(BaseModel):
    id: str
    client_id: str
    period: date
    status: str
    prepared_by: str
    approved_by: str | None
    total_gross: Decimal
    total_net: Decimal
    total_employer_cost: Decimal
    flags: list[str]
    slips: list[PayslipOut]


class RunSummaryOut(BaseModel):
    id: str
    client_id: str
    period: date
    status: str
    prepared_by: str
    approved_by: str | None
    employees: int
    total_gross: Decimal
    total_net: Decimal
    total_employer_cost: Decimal


class FilingOut(BaseModel):
    id: str
    client_id: str
    kind: str
    period: str
    due_on: date
    status: str
    amount: Decimal | None
    challan_ref: str | None


class FilingUpdate(BaseModel):
    status: str
    challan_ref: str | None = None


class RuleIn(BaseModel):
    scope: str = Field(description="'central' or a state code such as TG")
    category: str
    valid_from: date
    params: dict
    source: str = ""


class RuleOut(BaseModel):
    id: str
    scope: str
    category: str
    category_label: str
    valid_from: date
    valid_to: date | None
    params: dict
    source: str
    created_by: str
    created_at: datetime | None


class RuleCreated(BaseModel):
    rule: RuleOut
    closed: RuleOut | None


class RuleEdit(BaseModel):
    params: dict
    source: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    status: str
    client_id: str | None
    employee_code: str | None
    is_platform_admin: bool
    impersonated_by: str | None = None


class LoginOut(BaseModel):
    token: str
    user: UserOut


class ClientSignupIn(BaseModel):
    client: ClientIn
    name: str
    email: str
    password: str


class EmployeeSignupIn(BaseModel):
    client_id: str
    employee_code: str
    name: str
    email: str
    password: str


class MeOut(BaseModel):
    client_id: str
    client_name: str
    employee: EmployeeOut


class MyPayslipOut(BaseModel):
    run_id: str
    period: date
    payslip: PayslipOut


class ClientUpdate(BaseModel):
    legal_name: str | None = None
    pan: str | None = None
    tan: str | None = None
    pf_code: str | None = None
    esi_code: str | None = None
    pt_registration: str | None = None


class EmployeeUpdate(BaseModel):
    name: str | None = None
    components: dict[str, Amount] | None = None
    flags: dict[str, bool | None] | None = None


class PlanIn(BaseModel):
    plan: str
    rate_per_employee: Decimal | None = None
    minimum_fee: Decimal | None = None
    onboarding_fee: Decimal | None = None
    billing_email: str = ""
    starts_on: date | None = None


class InvoiceIn(BaseModel):
    month: date


class InvoicePayment(BaseModel):
    paid_on: date
    reference: str = ""


class InviteIn(BaseModel):
    email: str


class InviteAcceptIn(BaseModel):
    name: str
    password: str


class ReviewIn(BaseModel):
    note: str = ""


class ProfileIn(BaseModel):
    phone: str = ""
    date_of_birth: str = ""
    address: str = ""
    city: str = ""
    pincode: str = ""
    emergency_name: str = ""
    emergency_phone: str = ""
    uan: str = ""
    esi_ip: str = ""
    bank_name: str = ""
    ifsc: str = ""
    pan: str = ""
    account_number: str = ""
    submit: bool = False

class TaxCalcIn(BaseModel):
    on: date | None = None
    annual_gross: str = ""
    basic_da: str = ""
    hra_received: str = ""
    professional_tax: str = ""
    employee_pf: str = ""
    rent_paid: str = ""
    sec_80c: str = ""
    sec_80ccd_1b: str = ""
    sec_80d_self: str = ""
    sec_80d_parents: str = ""
    home_loan_interest: str = ""
    age_group: str = "below_60"
    metro_city: bool = False
    parents_senior: bool = False

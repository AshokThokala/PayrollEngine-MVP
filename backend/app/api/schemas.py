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


class EmployeeOut(BaseModel):
    code: str
    name: str
    joined_on: date
    exited_on: date | None
    components: dict[str, Decimal]
    monthly_total: Decimal


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

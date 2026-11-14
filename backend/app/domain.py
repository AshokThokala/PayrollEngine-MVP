"""Business records stored by the service (clients, employees, runs, filings, audit)."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .engine.models import Employee, Payslip, SalaryStructure


class RunStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"


class FilingStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FILED = "filed"


@dataclass
class Client:
    id: str
    legal_name: str
    state: str
    pan: str = ""
    tan: str = ""
    pf_code: str = ""
    esi_code: str = ""
    pt_registration: str = ""


@dataclass
class EmployeeRecord:
    client_id: str
    employee: Employee
    structure: SalaryStructure
    joined_on: date
    exited_on: date | None = None

    @property
    def code(self) -> str:
        return self.employee.code

    def active_in(self, month_end: date) -> bool:
        month_start = month_end.replace(day=1)
        return self.joined_on <= month_end and (
            self.exited_on is None or self.exited_on >= month_start
        )


@dataclass
class PayrollRun:
    id: str
    client_id: str
    period: date  # month end
    status: RunStatus
    prepared_by: str
    slips: dict[str, Payslip] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    approved_by: str | None = None
    locked_at: datetime | None = None

    @property
    def total_gross(self) -> Decimal:
        return sum((s.gross for s in self.slips.values()), Decimal(0))

    @property
    def total_net(self) -> Decimal:
        return sum((s.net_pay for s in self.slips.values()), Decimal(0))

    @property
    def total_employer_cost(self) -> Decimal:
        return sum((s.employer_cost for s in self.slips.values()), Decimal(0))


@dataclass
class Filing:
    id: str
    client_id: str
    kind: str  # pf, esi, tds_deposit, pt, lwf, form_24q
    period: str  # e.g. "2026-10" or "2026-27 Q3"
    due_on: date
    status: FilingStatus = FilingStatus.PENDING
    amount: Decimal | None = None
    challan_ref: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    at: datetime
    user: str
    action: str
    entity: str
    detail: str = ""


@dataclass
class StatutoryRule:
    """One dated version of a compliance rule, e.g. PF from 2026-09-17 or TG professional tax."""

    scope: str  # "central" or a state code such as "TG"
    category: str  # pf, esi, wage_code, income_tax_new_regime, filing_due_dates, professional_tax, lwf
    valid_from: date
    params: dict
    valid_to: date | None = None
    source: str = ""
    created_by: str = "system"
    created_at: datetime | None = None

    @property
    def id(self) -> str:
        return f"{self.scope}:{self.category}:{self.valid_from.isoformat()}"


class Role(str, enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"  # employee sign-ups wait for the employer's admin
    DISABLED = "disabled"


@dataclass
class User:
    """A login. Admins with no client_id are platform admins (the payroll service team);
    admins with a client_id manage only that client; employees see only themselves."""

    id: str
    email: str
    name: str
    role: Role
    password_hash: str
    status: UserStatus = UserStatus.ACTIVE
    client_id: str | None = None
    employee_code: str | None = None
    created_at: datetime | None = None
    impersonated_by: str | None = None  # admin email when an admin is viewing as this employee

    @property
    def is_platform_admin(self) -> bool:
        return self.role == Role.ADMIN and self.client_id is None

    def can_manage(self, client_id: str) -> bool:
        return self.role == Role.ADMIN and (self.client_id is None or self.client_id == client_id)


@dataclass
class RunSummary:
    """A payroll run's header and totals, without its payslips (for lists)."""

    id: str
    client_id: str
    period: date
    status: RunStatus
    prepared_by: str
    approved_by: str | None
    locked_at: datetime | None
    employees: int
    total_gross: Decimal
    total_net: Decimal
    total_employer_cost: Decimal


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


@dataclass
class BillingPlan:
    """What a client pays for the payroll service."""

    client_id: str
    plan: str  # "software" or "managed"
    rate_per_employee: Decimal  # per employee per month
    minimum_fee: Decimal  # monthly minimum
    onboarding_fee: Decimal  # one-time, on the first invoice
    gst_rate: Decimal = Decimal("0.18")
    billing_email: str = ""
    starts_on: date | None = None


@dataclass
class Invoice:
    id: str  # client_id:YYYY-MM
    client_id: str
    period: date  # last day of the month billed
    status: InvoiceStatus
    lines: list[dict]  # {description, quantity, rate, amount}
    subtotal: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    number: str | None = None  # assigned when issued, e.g. CP4U/2026-27/0001
    issue_date: date | None = None
    due_date: date | None = None
    paid_on: date | None = None
    payment_ref: str | None = None


# --- employee invites and onboarding ---------------------------------------------------------

@dataclass
class Invite:
    """A one-time link that lets an employee create their login. Only the token's hash is kept."""

    id: str
    client_id: str
    employee_code: str
    email: str
    token_hash: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked: bool = False


class ProfileStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"  # admin sent it back with a note
    VERIFIED = "verified"


@dataclass
class EmployeeProfile:
    """What an employee fills in when they join. pan_enc and account_enc are encrypted at rest."""

    client_id: str
    employee_code: str
    status: ProfileStatus = ProfileStatus.DRAFT
    details: dict = field(default_factory=dict)  # phone, dob, address, emergency contact, UAN, ESI IP, bank, IFSC
    pan_enc: str | None = None
    account_enc: str | None = None
    submitted_at: datetime | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    note: str = ""


# --- deduction master and standing employee deductions -----------------------------------------

class DeductionCategory(str, enum.Enum):
    STATUTORY = "statutory"  # worked out by the payroll engine from the compliance rules
    VOLUNTARY = "voluntary"  # the employee chose it (VPF, NPS, insurance, donations, ...)
    RECOVERY = "recovery"    # money the employer gets back (advance, loan EMI, notice pay, ...)


class DeductionCalc(str, enum.Enum):
    STATUTORY = "statutory"          # engine computes it; no amount to enter
    FIXED = "fixed"                  # rupees per month
    PERCENT_BASIC = "percent_basic"  # % of the month's basic + DA
    PERCENT_GROSS = "percent_gross"  # % of the month's gross


@dataclass
class DeductionType:
    """One kind of deduction an employee can have, from the master list."""

    code: str
    name: str
    category: DeductionCategory
    calc: DeductionCalc
    payslip_label: str = ""
    default_value: Decimal | None = None   # rupees, or percent for percent calcs
    max_amount: Decimal | None = None      # cap in rupees per month
    tax_section: str = ""                  # e.g. 80C, 80CCD(1), 80D, 80G (for information)
    description: str = ""
    active: bool = True
    system: bool = False                   # shipped with the app; code and calculation are fixed


@dataclass
class EmployeeDeduction:
    """A deduction taken from one employee's pay every month between two months."""

    id: str
    client_id: str
    employee_code: str
    deduction_code: str
    value: Decimal                 # rupees (fixed) or percent
    start_month: date              # first day of the first month
    end_month: date | None = None  # first day of the last month; None = until stopped
    note: str = ""
    created_by: str = ""


@dataclass
class ClientDeduction:
    """A client's choice of a master deduction type: switched on for its employees, with its own
    default, cap and payslip name (blank = use the master's)."""

    client_id: str
    deduction_code: str
    enabled: bool = True
    default_value: Decimal | None = None
    max_amount: Decimal | None = None
    payslip_label: str = ""


# --- pay codes (earnings): master, client, employee -------------------------------------------

class PayCodeKind(str, enum.Enum):
    FIXED = "fixed"        # part of the monthly salary structure (basic, HRA, allowances)
    VARIABLE = "variable"  # entered for a payroll month (bonus, incentive, arrears, overtime)


class PayCodeTax(str, enum.Enum):
    TAXABLE = "taxable"
    PARTLY_EXEMPT = "partly_exempt"  # exempt up to a limit or on proof (HRA, LTA, children education)
    EXEMPT = "exempt"                # reimbursements on bills, within limits


@dataclass
class PayCode:
    """One kind of pay an employee can get, from the master list."""

    code: str
    name: str
    kind: PayCodeKind
    tax: PayCodeTax = PayCodeTax.TAXABLE
    calc: str = "fixed"                   # default calculation: "fixed" (₹) or "percent_basic"
    default_value: Decimal | None = None
    payslip_label: str = ""
    tax_section: str = ""                 # e.g. 10(13A) for HRA, 10(5) for LTA
    description: str = ""
    core: bool = False                    # on for every client unless the client switches it off
    active: bool = True
    system: bool = False


@dataclass
class ClientPayCode:
    client_id: str
    pay_code: str
    enabled: bool = True
    default_value: Decimal | None = None
    payslip_label: str = ""


# --- time entry ---------------------------------------------------------------------------------

DAY_STATUSES = {
    "P": "Present", "A": "Absent (unpaid)", "HD": "Half day (half unpaid)", "L": "Paid leave",
    "H": "Holiday", "WO": "Weekly off",
}


class TimesheetStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"


@dataclass
class Timesheet:
    """One employee's time for one month. `days` maps the day number ("1".."31") to
    {"status": P/A/HD/L/H/WO, "hours": regular hours, "ot": overtime hours}."""

    client_id: str
    employee_code: str
    month: date  # first day of the month
    days: dict = field(default_factory=dict)
    status: TimesheetStatus = TimesheetStatus.DRAFT
    note: str = ""
    updated_by: str = ""
    approved_by: str | None = None


@dataclass
class ClientLocation:
    """A place where a client's employees work (head office, branch, factory, site).
    The location's state decides Professional Tax and Labour Welfare Fund for employees there."""

    id: str
    client_id: str
    name: str
    state: str
    address: str = ""
    city: str = ""
    pincode: str = ""
    pt_registration: str = ""    # PT employer registration in that state
    lwf_registration: str = ""
    esi_code: str = ""           # ESI sub-code for a branch, if any
    se_registration: str = ""    # Shops and Establishments registration
    head_office: bool = False
    active: bool = True

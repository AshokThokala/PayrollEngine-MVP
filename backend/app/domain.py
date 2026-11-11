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

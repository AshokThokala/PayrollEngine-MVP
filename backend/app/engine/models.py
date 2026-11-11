"""Plain data types used by the engine (no database, no web framework)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .money import D, ZERO

# Components that count as "wages" under the Code on Wages.
WAGE_COMPONENTS = ("basic", "da", "retaining_allowance")


@dataclass
class SalaryStructure:
    """Fixed monthly salary, split into named components (rupees per month)."""

    components: dict[str, Decimal]

    def __post_init__(self):
        self.components = {k: D(v) for k, v in self.components.items()}

    @property
    def total(self) -> Decimal:
        return sum(self.components.values(), ZERO)


@dataclass
class Employee:
    code: str
    name: str
    state: str = "TG"
    pf_member: bool = True
    eps_member: bool = True  # False once the employee is 58+ or opted out earlier
    pf_on_full_wages: bool = False  # voluntary PF above the wage ceiling (joint option)
    esi_covered: bool | None = None  # None = decide from wages
    pt_applicable: bool = True
    lwf_applicable: bool = True
    tax_regime: str = "new"  # "new" (default) or "old"
    tax_age_group: str = "below_60"  # below_60, 60_to_80, 80_plus (old-regime slabs, 80D)
    metro_city: bool = False  # HRA exemption share (old regime)
    parents_senior: bool = False  # 80D parents limit
    # Annual amounts declared for the old regime: rent_paid, sec_80c, sec_80ccd_1b,
    # sec_80d_self, sec_80d_parents, home_loan_interest
    tax_declarations: dict = field(default_factory=dict)


@dataclass
class PayInputs:
    """Variable inputs for one month."""

    period: date  # any day in the pay month; the last day is used for rule lookup
    days_in_month: int
    paid_days: Decimal
    overtime: Decimal = ZERO
    other_earnings: dict[str, Decimal] = field(default_factory=dict)
    other_deductions: dict[str, Decimal] = field(default_factory=dict)
    # For TDS projection
    fy_month_index: int = 1  # April = 1 ... March = 12
    ytd_taxable_gross: Decimal = ZERO  # gross paid in earlier months of this FY
    ytd_tds: Decimal = ZERO
    ytd_basic_da: Decimal = ZERO  # for HRA exemption
    ytd_hra: Decimal = ZERO
    ytd_pt: Decimal = ZERO
    ytd_pf: Decimal = ZERO

    def __post_init__(self):
        self.paid_days = D(self.paid_days)
        self.overtime = D(self.overtime)
        self.ytd_taxable_gross = D(self.ytd_taxable_gross)
        self.ytd_tds = D(self.ytd_tds)
        for name in ("ytd_basic_da", "ytd_hra", "ytd_pt", "ytd_pf"):
            setattr(self, name, D(getattr(self, name)))
        self.other_earnings = {k: D(v) for k, v in self.other_earnings.items()}
        self.other_deductions = {k: D(v) for k, v in self.other_deductions.items()}
        if not 0 <= self.paid_days <= self.days_in_month:
            raise ValueError("paid_days must be between 0 and days_in_month")
        if not 1 <= self.fy_month_index <= 12:
            raise ValueError("fy_month_index must be 1..12")


@dataclass
class Line:
    code: str
    label: str
    amount: Decimal
    rule: str | None = None


@dataclass
class Payslip:
    employee_code: str
    period: date
    earnings: list[Line]
    deductions: list[Line]
    employer_contributions: list[Line]
    warnings: list[str]
    statutory_wages: Decimal

    @property
    def gross(self) -> Decimal:
        return sum((l.amount for l in self.earnings), ZERO)

    @property
    def total_deductions(self) -> Decimal:
        return sum((l.amount for l in self.deductions), ZERO)

    @property
    def net_pay(self) -> Decimal:
        return self.gross - self.total_deductions

    @property
    def employer_cost(self) -> Decimal:
        return self.gross + sum((l.amount for l in self.employer_contributions), ZERO)

    def amount(self, code: str) -> Decimal:
        for line in (*self.earnings, *self.deductions, *self.employer_contributions):
            if line.code == code:
                return line.amount
        return ZERO

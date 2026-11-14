"""Deductions at three levels:
  1. Master (platform): every kind of deduction an employee in India can have.
  2. Client: which master deductions a client uses, with its own default, cap and payslip name.
  3. Employee: standing deductions for an employee, from the deductions their client uses.

Statutory deductions (PF, ESI, PT, LWF, TDS) are worked out by the payroll engine; their entries here
describe them and let admins rename them. Voluntary deductions and recoveries are set per employee
with a monthly amount or a percentage, between a first and a last month, and every payroll run in
that window takes them automatically.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import dataclasses

from ..domain import ClientDeduction, DeductionCalc, DeductionCategory, DeductionType, EmployeeDeduction, User
from ..engine.money import D, paise
from .auth_service import AccessDenied
from .payroll_service import PayrollService, ServiceError

SEED_FILE = Path(__file__).resolve().parent.parent / "rules" / "deduction_types.json"
CODE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
CALC_LABELS = {"statutory": "Worked out by payroll", "fixed": "Fixed ₹ per month",
               "percent_basic": "% of basic + DA", "percent_gross": "% of gross"}
TAX_SECTIONS = ["", "80C", "80CCD(1)", "80CCD(1B)", "80D", "80G", "16(iii)"]


def seed_deduction_types(repo) -> int:
    """Add the shipped deduction types that are missing. Never changes ones already there."""
    added = 0
    for raw in json.loads(SEED_FILE.read_text())["types"]:
        if repo.get_deduction_type(raw["code"]):
            continue
        try:
            repo.save_deduction_type(DeductionType(
                code=raw["code"], name=raw["name"], category=DeductionCategory(raw["category"]),
                calc=DeductionCalc(raw["calc"]), payslip_label=raw.get("payslip_label", ""),
                default_value=None if raw.get("default_value") is None else D(raw["default_value"]),
                max_amount=None if raw.get("max_amount") is None else D(raw["max_amount"]),
                tax_section=raw.get("tax_section", ""), description=raw.get("description", ""), system=True))
        except Exception:  # another worker seeded it at the same moment
            if repo.get_deduction_type(raw["code"]) is None:
                raise
            continue
        added += 1
    return added


def _month(value, field: str, errors: dict) -> date | None:
    if value in (None, ""):
        return None
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:7] + "-01")
    except ValueError:
        errors[field] = "Choose a month"
        return None
    return d.replace(day=1)


def _amount(value, field: str, errors: dict) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        d = D(value)
    except (InvalidOperation, ValueError, TypeError):
        errors[field] = "Enter a number"
        return None
    if d < 0:
        errors[field] = "Cannot be negative"
    return d


def client_types(repo, client_id: str) -> dict[str, DeductionType]:
    """Deduction types a client's employees can be given: active master types the client has switched
    on, with the client's own default, cap and payslip name filled in."""
    settings = {cd.deduction_code: cd for cd in repo.list_client_deductions(client_id)}
    out = {}
    for t in repo.list_deduction_types():
        cd = settings.get(t.code)
        if t.calc == DeductionCalc.STATUTORY or not t.active or cd is None or not cd.enabled:
            continue
        out[t.code] = dataclasses.replace(
            t, default_value=t.default_value if cd.default_value is None else cd.default_value,
            max_amount=t.max_amount if cd.max_amount is None else cd.max_amount,
            payslip_label=cd.payslip_label or t.payslip_label)
    return out


def monthly_amount(t: DeductionType, value: Decimal, basic_da: Decimal, gross: Decimal) -> Decimal:
    """Rupees to deduct this month for one standing deduction."""
    if t.calc == DeductionCalc.PERCENT_BASIC:
        amount = basic_da * value / 100
    elif t.calc == DeductionCalc.PERCENT_GROSS:
        amount = gross * value / 100
    else:
        amount = value
    if t.max_amount is not None:
        amount = min(amount, t.max_amount)
    return paise(max(amount, Decimal(0)))


class DeductionService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo

    # --- master ----------------------------------------------------------------------------------
    def types(self, include_inactive: bool = True) -> list[DeductionType]:
        return [t for t in self.repo.list_deduction_types() if include_inactive or t.active]

    def save_type(self, actor: User, data: dict, code: str | None = None) -> DeductionType:
        """Add (code=None) or edit a deduction type. Platform admins only."""
        if not actor.is_platform_admin:
            raise AccessDenied("Only the ClearPay4U team can change the deduction master")
        errors: dict[str, str] = {}
        existing = self.repo.get_deduction_type(code) if code else None
        if code and existing is None:
            raise ServiceError(f"No deduction type {code!r}")
        name = str(data.get("name") or "").strip()
        if not name:
            errors["name"] = "Enter a name"
        label = str(data.get("payslip_label") or "").strip()
        description = str(data.get("description") or "").strip()
        tax_section = str(data.get("tax_section") or "").strip()
        active = bool(data.get("active", True))

        if existing and existing.system and existing.category == DeductionCategory.STATUTORY:
            # Statutory: worked out by the engine. Only the wording can change; it can't be switched off.
            if errors:
                raise ServiceError("Check the highlighted fields", errors=errors)
            existing.name, existing.payslip_label, existing.description = name, label, description
            return self._store(actor, existing, "deduction_type.update")

        new_code = existing.code if existing else str(data.get("code") or "").strip().lower()
        if not existing:
            if not CODE.match(new_code):
                errors["type_code"] = "2–31 characters: lower-case letters, digits and _, starting with a letter"
            elif self.repo.get_deduction_type(new_code):
                errors["type_code"] = "A deduction type with this code already exists"
        try:
            category = DeductionCategory(data.get("category") or "")
            if category == DeductionCategory.STATUTORY:
                errors["category"] = "Statutory deductions come from the compliance rules; choose voluntary or recovery"
        except ValueError:
            errors["category"] = "Choose voluntary or recovery"
            category = DeductionCategory.VOLUNTARY
        if existing and existing.system:
            calc = existing.calc  # shipped types keep their calculation so existing assignments stay right
        else:
            try:
                calc = DeductionCalc(data.get("calc") or "")
                if calc == DeductionCalc.STATUTORY:
                    raise ValueError
            except ValueError:
                errors["calc"] = "Choose fixed amount, % of basic + DA or % of gross"
                calc = DeductionCalc.FIXED
        default_value = _amount(data.get("default_value"), "default_value", errors)
        max_amount = _amount(data.get("max_amount"), "max_amount", errors)
        if calc != DeductionCalc.FIXED and default_value is not None and default_value > 100 \
                and "default_value" not in errors:
            errors["default_value"] = "A percentage cannot be more than 100"
        if tax_section not in TAX_SECTIONS:
            errors["tax_section"] = "Choose a section from the list"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        t = DeductionType(code=new_code, name=name, category=category, calc=calc, payslip_label=label,
                          default_value=default_value, max_amount=max_amount, tax_section=tax_section,
                          description=description, active=active, system=bool(existing and existing.system))
        return self._store(actor, t, "deduction_type.update" if existing else "deduction_type.create")

    def _store(self, actor: User, t: DeductionType, action: str) -> DeductionType:
        self.repo.save_deduction_type(t)
        self.payroll._audit(actor.email, action, f"deduction_type/{t.code}", t.name)
        return t

    # --- client level ---------------------------------------------------------------------------------
    def client_settings(self, client_id: str) -> list[dict]:
        """Every master deduction with this client's choice. Statutory ones always apply."""
        self.repo.get_client(client_id)
        settings = {cd.deduction_code: cd for cd in self.repo.list_client_deductions(client_id)}
        used: dict[str, int] = {}
        for d in self.repo.list_employee_deductions(client_id):
            used[d.deduction_code] = used.get(d.deduction_code, 0) + 1
        rows = []
        for t in self.repo.list_deduction_types():
            if not t.active and t.code not in settings:
                continue
            cd = settings.get(t.code)
            statutory = t.calc == DeductionCalc.STATUTORY
            rows.append({"type": t, "statutory": statutory,
                         "enabled": statutory or bool(cd and cd.enabled and t.active),
                         "default_value": cd.default_value if cd else None,
                         "max_amount": cd.max_amount if cd else None,
                         "payslip_label": cd.payslip_label if cd else "",
                         "employees": used.get(t.code, 0)})
        return rows

    def set_client(self, actor: User, client_id: str, code: str, data: dict) -> ClientDeduction:
        """Switch a master deduction on or off for a client, with its own default, cap and payslip name."""
        self.repo.get_client(client_id)
        t = self.repo.get_deduction_type(code)
        if t is None:
            raise ServiceError(f"No deduction type {code!r}")
        if t.calc == DeductionCalc.STATUTORY:
            raise ServiceError("Statutory deductions always apply; they cannot be switched off for a client")
        errors: dict[str, str] = {}
        enabled = bool(data.get("enabled", True))
        if enabled and not t.active:
            errors["enabled"] = "This deduction is switched off in the master list"
        default_value = _amount(data.get("default_value"), "default_value", errors)
        max_amount = _amount(data.get("max_amount"), "max_amount", errors)
        if t.calc != DeductionCalc.FIXED and default_value is not None and default_value > 100 \
                and "default_value" not in errors:
            errors["default_value"] = "A percentage cannot be more than 100"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        cd = ClientDeduction(client_id, code, enabled, default_value, max_amount,
                             str(data.get("payslip_label") or "").strip())
        self.repo.save_client_deduction(cd)
        self.payroll._audit(actor.email, "client_deduction.update", f"client/{client_id}",
                            f"{code} {'on' if enabled else 'off'}")
        return cd

    def for_client(self, client_id: str) -> list[EmployeeDeduction]:
        """Every standing deduction of every employee of the client."""
        self.repo.get_client(client_id)
        return self.repo.list_employee_deductions(client_id)

    # --- per employee ---------------------------------------------------------------------------------
    def for_employee(self, client_id: str, code: str) -> list[EmployeeDeduction]:
        self.repo.get_employee(client_id, code)
        return self.repo.list_employee_deductions(client_id, code)

    def save_for_employee(self, actor: User, client_id: str, code: str, data: dict,
                          deduction_id: str | None = None) -> EmployeeDeduction:
        record = self.repo.get_employee(client_id, code)
        errors: dict[str, str] = {}
        old = self.repo.get_employee_deduction(deduction_id) if deduction_id else None
        if old and (old.client_id, old.employee_code) != (client_id, code):
            raise ServiceError("This deduction belongs to another employee")
        wanted = data.get("deduction_code") or (old.deduction_code if old else "")
        master = self.repo.get_deduction_type(wanted) if wanted else None
        t = client_types(self.repo, client_id).get(wanted)
        if master is None:
            errors["deduction_code"] = "Choose a deduction"
        elif master.calc == DeductionCalc.STATUTORY:
            errors["deduction_code"] = "Statutory deductions are worked out automatically"
        elif t is None:
            errors["deduction_code"] = "This client does not use this deduction; switch it on under Client deductions"
        value = _amount(data.get("value"), "value", errors)
        if value is None and t is not None and "value" not in errors:
            value = t.default_value
        if value is None and "value" not in errors:
            errors["value"] = "Enter an amount"
        elif value is not None and value == 0 and "value" not in errors:
            errors["value"] = "Enter more than zero"
        elif t is not None and value is not None and t.calc != DeductionCalc.FIXED and value > 100:
            errors["value"] = "A percentage cannot be more than 100"
        start = _month(data.get("start_month"), "start_month", errors)
        end = _month(data.get("end_month"), "end_month", errors)
        if start is None and "start_month" not in errors:
            errors["start_month"] = "Choose the first month"
        if start and end and end < start:
            errors["end_month"] = "The last month cannot be before the first month"
        if start and record.joined_on and start < record.joined_on.replace(day=1):
            errors["start_month"] = "Cannot start before the employee joined"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        d = EmployeeDeduction(id=old.id if old else uuid.uuid4().hex, client_id=client_id, employee_code=code,
                              deduction_code=t.code, value=value, start_month=start, end_month=end,
                              note=str(data.get("note") or "").strip(),
                              created_by=old.created_by if old else actor.email)
        self.repo.save_employee_deduction(d)
        self.payroll._audit(actor.email, "employee_deduction.update" if old else "employee_deduction.create",
                            f"employee/{client_id}/{code}", f"{t.code} {value}")
        return d

    def delete_for_employee(self, actor: User, client_id: str, code: str, deduction_id: str) -> None:
        d = self.repo.get_employee_deduction(deduction_id)
        if (d.client_id, d.employee_code) != (client_id, code):
            raise ServiceError("This deduction belongs to another employee")
        self.repo.delete_employee_deduction(deduction_id)
        self.payroll._audit(actor.email, "employee_deduction.delete", f"employee/{client_id}/{code}",
                            d.deduction_code)

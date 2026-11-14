"""Pay codes (earnings) at three levels:
  1. Master (platform): every kind of pay an employee in India can get, with its tax treatment.
  2. Client: which pay codes a client uses, with its own default and payslip name. Core codes
     (basic, DA, HRA, special allowance, conveyance) are on for every client unless switched off.
  3. Employee: the amounts. Fixed pay codes make up the monthly salary structure; variable ones
     (bonus, incentive, arrears) are entered for a payroll month.
"""
from __future__ import annotations

import dataclasses
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..domain import ClientPayCode, PayCode, PayCodeKind, PayCodeTax, User
from ..engine.money import D
from .auth_service import AccessDenied
from .payroll_service import PayrollService, ServiceError

SEED_FILE = Path(__file__).resolve().parent.parent / "rules" / "pay_codes.json"
CODE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
ALWAYS_ON = {"basic"}  # a client cannot switch these off
TAX_LABELS = {"taxable": "Taxable", "partly_exempt": "Partly exempt (old regime)", "exempt": "Exempt on bills"}
CALC_LABELS = {"fixed": "Fixed ₹ per month", "percent_basic": "% of basic"}


def seed_pay_codes(repo) -> int:
    added = 0
    for raw in json.loads(SEED_FILE.read_text())["codes"]:
        if repo.get_pay_code(raw["code"]):
            continue
        try:
            repo.save_pay_code(PayCode(
                code=raw["code"], name=raw["name"], kind=PayCodeKind(raw["kind"]), tax=PayCodeTax(raw.get("tax", "taxable")),
                calc=raw.get("calc", "fixed"),
                default_value=None if raw.get("default_value") is None else D(raw["default_value"]),
                payslip_label=raw.get("payslip_label", ""), tax_section=raw.get("tax_section", ""),
                description=raw.get("description", ""), core=bool(raw.get("core")), system=True))
        except Exception:  # another worker seeded it at the same moment
            if repo.get_pay_code(raw["code"]) is None:
                raise
            continue
        added += 1
    return added


def client_pay_codes(repo, client_id: str) -> dict[str, PayCode]:
    """Pay codes a client's employees can get, with the client's default and payslip name filled in."""
    settings = {cp.pay_code: cp for cp in repo.list_client_pay_codes(client_id)}
    out = {}
    for p in repo.list_pay_codes():
        cp = settings.get(p.code)
        enabled = cp.enabled if cp else p.core
        if not p.active or not enabled:
            continue
        out[p.code] = dataclasses.replace(
            p, default_value=p.default_value if cp is None or cp.default_value is None else cp.default_value,
            payslip_label=(cp.payslip_label if cp and cp.payslip_label else p.payslip_label))
    return out


def check_codes(repo, client_id: str, codes, kind: PayCodeKind, field: str) -> None:
    """Every code must be a pay code of this kind that the client uses. Skipped when no master exists."""
    if not repo.list_pay_codes():
        return
    allowed = {c: p for c, p in client_pay_codes(repo, client_id).items() if p.kind == kind}
    bad = sorted(set(codes) - set(allowed))
    if bad:
        what = "salary" if kind == PayCodeKind.FIXED else "variable pay"
        raise ServiceError(f"Not a {what} pay code this client uses: {', '.join(bad)}. "
                           "Switch it on under Client pay codes.", field=field)


def _amount(value, field, errors):
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


class PayCodeService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo

    def wage_codes(self) -> set[str]:
        """Codes that count as wages under the Code on Wages (from the wage_code rule in force)."""
        return set(self.payroll.rules.central("wage_code", self.payroll.clock().date())["wage_components"])

    # --- master -------------------------------------------------------------------------------
    def codes(self) -> list[PayCode]:
        return self.repo.list_pay_codes()

    def save_code(self, actor: User, data: dict, code: str | None = None) -> PayCode:
        if not actor.is_platform_admin:
            raise AccessDenied("Only the ClearPay4U team can change the pay code master")
        errors: dict[str, str] = {}
        existing = self.repo.get_pay_code(code) if code else None
        if code and existing is None:
            raise ServiceError(f"No pay code {code!r}")
        name = str(data.get("name") or "").strip()
        if not name:
            errors["name"] = "Enter a name"
        new_code = existing.code if existing else str(data.get("code") or "").strip().lower()
        if not existing:
            if not CODE.match(new_code):
                errors["type_code"] = "2–31 characters: lower-case letters, digits and _, starting with a letter"
            elif self.repo.get_pay_code(new_code):
                errors["type_code"] = "A pay code with this code already exists"
        try:
            kind = existing.kind if existing and existing.system else PayCodeKind(data.get("kind") or "")
        except ValueError:
            errors["kind"] = "Choose salary (fixed) or variable"
            kind = PayCodeKind.FIXED
        try:
            tax = PayCodeTax(data.get("tax") or "taxable")
        except ValueError:
            errors["tax"] = "Choose the tax treatment"
            tax = PayCodeTax.TAXABLE
        calc = str(data.get("calc") or "fixed")
        if calc not in CALC_LABELS:
            errors["calc"] = "Choose fixed ₹ or % of basic"
        if kind == PayCodeKind.VARIABLE and calc != "fixed":
            errors["calc"] = "Variable pay is entered in ₹ for the month"
        default_value = _amount(data.get("default_value"), "default_value", errors)
        if calc == "percent_basic" and default_value is not None and default_value > 100 \
                and "default_value" not in errors:
            errors["default_value"] = "A percentage cannot be more than 100"
        core = bool(data.get("core", existing.core if existing else False)) and kind == PayCodeKind.FIXED
        active = bool(data.get("active", True))
        if existing and existing.code in ALWAYS_ON and not active:
            errors["active"] = "Basic cannot be switched off"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        p = PayCode(code=new_code, name=name, kind=kind, tax=tax, calc=calc, default_value=default_value,
                    payslip_label=str(data.get("payslip_label") or "").strip(),
                    tax_section=str(data.get("tax_section") or "").strip(),
                    description=str(data.get("description") or "").strip(), core=core, active=active,
                    system=bool(existing and existing.system))
        self.repo.save_pay_code(p)
        self.payroll._audit(actor.email, "pay_code.update" if existing else "pay_code.create",
                            f"pay_code/{p.code}", p.name)
        return p

    # --- client -------------------------------------------------------------------------------
    def client_settings(self, client_id: str) -> list[dict]:
        self.repo.get_client(client_id)
        settings = {cp.pay_code: cp for cp in self.repo.list_client_pay_codes(client_id)}
        used: dict[str, int] = {}
        for r in self.repo.list_employees(client_id):
            if r.exited_on is None:
                for c in r.structure.components:
                    used[c] = used.get(c, 0) + 1
        rows = []
        for p in self.repo.list_pay_codes():
            cp = settings.get(p.code)
            if not p.active and cp is None:
                continue
            rows.append({"code": p, "enabled": p.active and (cp.enabled if cp else p.core),
                         "default_value": cp.default_value if cp else None,
                         "payslip_label": cp.payslip_label if cp else "", "employees": used.get(p.code, 0),
                         "locked": p.code in ALWAYS_ON})
        return rows

    def set_client(self, actor: User, client_id: str, code: str, data: dict) -> ClientPayCode:
        self.repo.get_client(client_id)
        p = self.repo.get_pay_code(code)
        if p is None:
            raise ServiceError(f"No pay code {code!r}")
        errors: dict[str, str] = {}
        enabled = bool(data.get("enabled", True))
        if not enabled and code in ALWAYS_ON:
            errors["enabled"] = "Basic is always used"
        if enabled and not p.active:
            errors["enabled"] = "This pay code is switched off in the master list"
        default_value = _amount(data.get("default_value"), "default_value", errors)
        if p.calc == "percent_basic" and default_value is not None and default_value > 100 \
                and "default_value" not in errors:
            errors["default_value"] = "A percentage cannot be more than 100"
        if not enabled and "enabled" not in errors:
            using = [r.code for r in self.repo.list_employees(client_id)
                     if r.exited_on is None and code in r.structure.components]
            if using and p.kind == PayCodeKind.FIXED:
                errors["enabled"] = (f"{len(using)} employee(s) have {p.name} in their salary "
                                     f"({', '.join(using[:5])}{'…' if len(using) > 5 else ''}). Remove it from them first.")
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        cp = ClientPayCode(client_id, code, enabled, default_value, str(data.get("payslip_label") or "").strip())
        self.repo.save_client_pay_code(cp)
        self.payroll._audit(actor.email, "client_pay_code.update", f"client/{client_id}",
                            f"{code} {'on' if enabled else 'off'}")
        return cp

    # --- employee -----------------------------------------------------------------------------
    def employee_grid(self, client_id: str, include_exited: bool = False) -> dict:
        """Every employee's salary by pay code, with the fixed pay codes the client uses as columns."""
        self.repo.get_client(client_id)
        codes = [p for p in client_pay_codes(self.repo, client_id).values() if p.kind == PayCodeKind.FIXED]
        rows = []
        for r in self.repo.list_employees(client_id):
            if r.exited_on and not include_exited:
                continue
            rows.append({"code": r.code, "name": r.employee.name, "exited_on": r.exited_on,
                         "components": dict(r.structure.components), "total": r.structure.total})
        return {"pay_codes": codes, "employees": sorted(rows, key=lambda x: x["code"])}

    def set_employee_pay(self, actor: User, client_id: str, code: str, components: dict) -> list[str]:
        clean: dict[str, Decimal] = {}
        errors: dict[str, str] = {}
        for k, v in (components or {}).items():
            amount = _amount(v, k, errors)
            if amount:
                clean[k] = amount
        if errors:
            raise ServiceError("Check the highlighted amounts", errors=errors)
        return self.payroll.update_employee(client_id, code, actor.email, components=clean)

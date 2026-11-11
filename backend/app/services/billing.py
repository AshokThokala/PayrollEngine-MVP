"""Billing for the payroll service: plans and monthly invoices with GST.

Plans (from the MVP feature doc - adjust per client):
  software  ₹60 per employee per month, no minimum, no onboarding fee
  managed   ₹150 per employee per month, ₹5,000 monthly minimum, ₹15,000 one-time onboarding

An invoice bills the employees paid in that month's locked payroll run. GST 18%: CGST + SGST
when the client is in the provider's state (PROVIDER_STATE, default TG), otherwise IGST.
Invoices go draft -> issued (gets the next number for the financial year) -> paid, or void.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from ..domain import BillingPlan, Invoice, InvoiceStatus, RunStatus
from ..engine.money import D, paise
from ..engine.payroll import month_end
from .payroll_service import PayrollService, ServiceError

PLANS = {
    "software": {"label": "Software only", "rate_per_employee": 60, "minimum_fee": 0, "onboarding_fee": 0,
                 "description": "Payroll engine, payslips and statutory files; the client files returns."},
    "managed": {"label": "Managed payroll and compliance", "rate_per_employee": 150, "minimum_fee": 5000,
                "onboarding_fee": 15000,
                "description": "Software plus our team runs payroll and files PF, ESI, PT, LWF and TDS."},
}
PAYMENT_TERMS_DAYS = 15
ONBOARDING_LINE = "One-time onboarding"


def provider_state() -> str:
    return os.environ.get("PROVIDER_STATE", "TG")


def _fy_label(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


class BillingService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo

    # --- plans ---------------------------------------------------------------------------
    def set_plan(self, client_id: str, user: str, *, plan: str, rate_per_employee=None, minimum_fee=None,
                 onboarding_fee=None, billing_email: str = "", starts_on: date | None = None) -> BillingPlan:
        self.repo.get_client(client_id)
        if plan not in PLANS:
            raise ServiceError(f"Choose one of: {', '.join(PLANS)}", field="plan")
        preset = PLANS[plan]
        errors = {}
        values = {}
        for key, given in (("rate_per_employee", rate_per_employee), ("minimum_fee", minimum_fee),
                           ("onboarding_fee", onboarding_fee)):
            try:
                amount = D(preset[key] if given in (None, "") else given)
            except Exception:  # noqa: BLE001 - parse error is a user input error
                errors[key] = "Enter an amount"
                continue
            if amount < 0:
                errors[key] = "Must be 0 or more"
            values[key] = paise(amount)
        if billing_email and "@" not in billing_email:
            errors["billing_email"] = "Enter a valid email address"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        result = BillingPlan(client_id, plan, values["rate_per_employee"], values["minimum_fee"],
                             values["onboarding_fee"], Decimal("0.18"), billing_email.strip(),
                             starts_on or self.payroll.clock().date())
        self.repo.save_billing_plan(result)
        self.payroll._audit(user, "billing.plan", client_id,
                            f"{plan}: ₹{result.rate_per_employee}/employee, minimum ₹{result.minimum_fee}")
        return result

    # --- invoices ----------------------------------------------------------------------------
    def generate(self, client_id: str, month: date, user: str) -> Invoice:
        """Create or refresh the draft invoice for a month from its locked payroll run."""
        client = self.repo.get_client(client_id)
        plan = self.repo.get_billing_plan(client_id)
        if plan is None:
            raise ServiceError("Set a billing plan for this client first", field="plan")
        end = month_end(month)
        invoice_id = f"{client_id}:{end:%Y-%m}"
        try:
            existing = self.repo.get_invoice(invoice_id)
        except LookupError:
            existing = None
        if existing and existing.status != InvoiceStatus.DRAFT:
            raise ServiceError(f"The {end:%B %Y} invoice is already {existing.status.value}", field="month")
        try:
            run = self.repo.get_run(f"{client_id}:{end:%Y-%m}")
        except LookupError:
            run = None
        if run is None or run.status != RunStatus.LOCKED:
            raise ServiceError(f"Lock the {end:%B %Y} payroll run before billing it", field="month")

        headcount = len(run.slips)
        label = PLANS[plan.plan]["label"]
        usage = paise(plan.rate_per_employee * headcount)
        def money_str(value) -> str:
            return str(paise(value))  # always two decimals, whatever the database returns

        lines = [{"description": f"{label} — {end:%B %Y}", "quantity": headcount,
                  "rate": money_str(plan.rate_per_employee), "amount": money_str(usage)}]
        if usage < plan.minimum_fee:
            top_up = plan.minimum_fee - usage
            lines.append({"description": "Minimum monthly fee top-up", "quantity": 1,
                          "rate": money_str(top_up), "amount": money_str(top_up)})
        already_charged = any(
            i.id != invoice_id and i.status in (InvoiceStatus.ISSUED, InvoiceStatus.PAID)
            and any(line["description"] == ONBOARDING_LINE for line in i.lines)
            for i in self.repo.list_invoices(client_id))
        if plan.onboarding_fee > 0 and not already_charged:
            lines.append({"description": ONBOARDING_LINE, "quantity": 1,
                          "rate": money_str(plan.onboarding_fee), "amount": money_str(plan.onboarding_fee)})

        subtotal = paise(sum((D(line["amount"]) for line in lines), Decimal(0)))
        tax = paise(subtotal * plan.gst_rate)
        if client.state == provider_state():
            cgst = paise(tax / 2)
            sgst, igst = tax - cgst, Decimal(0)
        else:
            cgst, sgst, igst = Decimal(0), Decimal(0), tax
        invoice = Invoice(invoice_id, client_id, end, InvoiceStatus.DRAFT, lines, subtotal, cgst, sgst, igst,
                          subtotal + tax)
        self.repo.save_invoice(invoice)
        self.payroll._audit(user, "invoice.draft", invoice_id, f"{headcount} employees, total ₹{invoice.total}")
        return invoice

    def issue(self, invoice_id: str, user: str) -> Invoice:
        invoice = self.repo.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise ServiceError(f"Only a draft can be issued (invoice is {invoice.status.value})")
        today = self.payroll.clock().date()
        prefix = f"CP4U/{_fy_label(today)}/"
        used = [int(i.number[len(prefix):]) for i in self.repo.list_invoices()
                if i.number and i.number.startswith(prefix)]
        invoice.number = f"{prefix}{(max(used) if used else 0) + 1:04d}"
        invoice.status, invoice.issue_date = InvoiceStatus.ISSUED, today
        invoice.due_date = today + timedelta(days=PAYMENT_TERMS_DAYS)
        self.repo.save_invoice(invoice)
        self.payroll._audit(user, "invoice.issue", invoice_id, invoice.number)
        return invoice

    def mark_paid(self, invoice_id: str, user: str, paid_on: date, reference: str) -> Invoice:
        invoice = self.repo.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.ISSUED:
            raise ServiceError(f"Only an issued invoice can be paid (invoice is {invoice.status.value})")
        if not (reference or "").strip():
            raise ServiceError("Enter the payment reference (UTR / cheque number)", field="reference")
        invoice.status, invoice.paid_on, invoice.payment_ref = InvoiceStatus.PAID, paid_on, reference.strip()
        self.repo.save_invoice(invoice)
        self.payroll._audit(user, "invoice.paid", invoice_id, f"{invoice.number} {reference.strip()}")
        return invoice

    def void(self, invoice_id: str, user: str) -> Invoice:
        invoice = self.repo.get_invoice(invoice_id)
        if invoice.status == InvoiceStatus.PAID:
            raise ServiceError("A paid invoice can't be voided; issue a credit note instead")
        invoice.status = InvoiceStatus.VOID  # an issued number stays used, so numbering has no gaps
        self.repo.save_invoice(invoice)
        self.payroll._audit(user, "invoice.void", invoice_id, invoice.number or "draft")
        return invoice

    def overview(self, today: date) -> list[dict]:
        """One row per client: plan, invoices outstanding and overdue amounts."""
        rows = []
        for client in self.repo.list_clients():
            plan = self.repo.get_billing_plan(client.id)
            invoices = self.repo.list_invoices(client.id)
            open_ = [i for i in invoices if i.status == InvoiceStatus.ISSUED]
            rows.append({
                "client_id": client.id, "client_name": client.legal_name,
                "plan": PLANS[plan.plan]["label"] if plan else None,
                "outstanding": sum((i.total for i in open_), Decimal(0)),
                "overdue": sum((i.total for i in open_ if i.due_date and i.due_date < today), Decimal(0)),
                "last_invoice": invoices[0].period.isoformat() if invoices else None,
            })
        return rows

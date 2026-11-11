"""Client onboarding checklist, worked out from the client's actual data.

Nothing is ticked by hand: a step is done when the data shows it is done, so the checklist
can never claim more than is true. Each step names the page where it is completed.
"""
from __future__ import annotations

from ..domain import Role, RunStatus, UserStatus
from ..engine.wages import check_structure
from .payroll_service import PayrollService


def client_checklist(payroll: PayrollService, client_id: str) -> dict:
    repo = payroll.repo
    client = repo.get_client(client_id)
    employees = [r for r in repo.list_employees(client_id) if not r.exited_on]
    admins = [u for u in repo.list_users(client_id) if u.role == Role.ADMIN and u.status == UserStatus.ACTIVE]
    plan = repo.get_billing_plan(client_id)
    runs = repo.list_run_summaries(client_id)
    wage_rule = payroll.rules.central("wage_code", payroll.clock().date())
    weak = [r.code for r in employees if check_structure(r.structure, wage_rule)]

    missing_company = [label for label, value in (("PAN", client.pan), ("TAN", client.tan)) if not value]
    missing_regs = [label for label, value in (("PF code", client.pf_code),
                                                ("PT registration", client.pt_registration)) if not value]

    steps = [
        {"key": "company", "title": "Company details",
         "description": "Legal name, PAN and TAN (needed for TDS deposits and Form 138).",
         "done": not missing_company,
         "detail": "Complete" if not missing_company else f"Missing: {', '.join(missing_company)}",
         "action": "clients"},
        {"key": "registrations", "title": "Statutory registrations",
         "description": "PF establishment code and Professional Tax registration. ESI code if any employee earns up to the ESI limit.",
         "done": not missing_regs,
         "detail": ("Complete" + ("" if client.esi_code else " (no ESI code yet)")) if not missing_regs
         else f"Missing: {', '.join(missing_regs)}",
         "action": "clients"},
        {"key": "admin", "title": "Client admin login",
         "description": "At least one person at the client can log in to approve payroll and staff accounts.",
         "done": bool(admins), "detail": f"{len(admins)} admin(s)" if admins else "No client admin yet",
         "action": "users"},
        {"key": "billing", "title": "Billing plan",
         "description": "The plan and rates this client is billed on.",
         "done": plan is not None, "detail": plan.plan.capitalize() if plan else "Not set", "action": "billing"},
        {"key": "employees", "title": "Employees added",
         "description": "Every employee with joining date and monthly salary.",
         "done": bool(employees), "detail": f"{len(employees)} active" if employees else "None yet",
         "action": "employees"},
        {"key": "salaries", "title": "Salary structures checked",
         "description": "Basic + DA is at least 50% of pay (Code on Wages), so PF and gratuity are right.",
         "done": bool(employees) and not weak,
         "detail": "All good" if employees and not weak else (f"Review: {', '.join(weak[:5])}" + ("…" if len(weak) > 5 else "")
                                                             if weak else "Add employees first"),
         "action": "employees"},
        {"key": "first_run", "title": "First payroll locked",
         "description": "A month calculated, approved and locked.",
         "done": any(r.status == RunStatus.LOCKED for r in runs),
         "detail": next((f"{r.period:%B %Y}" for r in runs if r.status == RunStatus.LOCKED), "Not yet"),
         "action": "runs"},
    ]
    done = sum(1 for s in steps if s["done"])
    next_step = next((s for s in steps if not s["done"]), None)
    return {"client_id": client.id, "client_name": client.legal_name, "steps": steps,
            "done": done, "total": len(steps), "percent": round(100 * done / len(steps)),
            "live": next_step is None, "next_step": next_step["title"] if next_step else None}


def all_clients(payroll: PayrollService) -> list[dict]:
    rows = []
    for client in payroll.repo.list_clients():
        c = client_checklist(payroll, client.id)
        rows.append({k: c[k] for k in ("client_id", "client_name", "done", "total", "percent", "live", "next_step")})
    return sorted(rows, key=lambda r: (r["live"], r["percent"], r["client_name"]))

"""Search box on the main screen: employees the user may see, by name or code."""
from __future__ import annotations

from ..domain import Role, User
from .auth_service import AccessDenied
from .payroll_service import PayrollService

MIN_LENGTH = 2


def search(svc: PayrollService, actor: User, query: str, limit: int = 10) -> dict:
    if actor.role != Role.ADMIN:
        raise AccessDenied("Admins only")
    q = (query or "").strip()
    if len(q) < MIN_LENGTH:
        return {"query": q, "employees": []}
    names = {c.id: c.legal_name for c in svc.repo.list_clients() if actor.can_manage(c.id)}
    scope = None if actor.is_platform_admin else [actor.client_id]
    employees = svc.repo.search_employees(q, scope, limit)
    return {"query": q,
            "employees": [{**e, "client_name": names.get(e["client_id"], e["client_id"]),
                           "active": e["exited_on"] is None} for e in employees]}

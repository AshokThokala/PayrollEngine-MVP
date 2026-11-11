"""Search box on the main screen: clients and employees the user may see."""
from __future__ import annotations

from ..domain import Role, User
from .auth_service import AccessDenied
from .payroll_service import PayrollService

MIN_LENGTH = 2


def search(svc: PayrollService, actor: User, query: str, limit: int = 8) -> dict:
    if actor.role != Role.ADMIN:
        raise AccessDenied("Admins only")
    q = (query or "").strip()
    if len(q) < MIN_LENGTH:
        return {"query": q, "clients": [], "employees": []}
    needle = q.lower()
    clients = [c for c in svc.repo.list_clients() if actor.can_manage(c.id)]
    names = {c.id: c.legal_name for c in clients}
    found = [c for c in clients
             if needle in c.id.lower() or needle in c.legal_name.lower() or needle in (c.pan or "").lower()]
    found.sort(key=lambda c: (not c.legal_name.lower().startswith(needle), c.legal_name.lower()))
    scope = None if actor.is_platform_admin else [actor.client_id]
    employees = svc.repo.search_employees(q, scope, limit)
    return {
        "query": q,
        "clients": [{"id": c.id, "legal_name": c.legal_name, "state": c.state} for c in found[:limit]],
        "employees": [{**e, "client_name": names.get(e["client_id"], e["client_id"]),
                       "active": e["exited_on"] is None} for e in employees],
    }

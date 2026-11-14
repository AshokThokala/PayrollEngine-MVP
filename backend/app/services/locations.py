"""Client locations: head office, branches, factories and sites.

Each employee works at one location. The location's state decides which state's Professional Tax and
Labour Welfare Fund rules apply to them (an employee in a Bengaluru branch pays Karnataka PT even if
the client is registered in Telangana).
"""
from __future__ import annotations

import re
import uuid

from ..domain import ClientLocation, User
from ..rule_schemas import STATE_NAMES
from .payroll_service import PayrollService, ServiceError

PINCODE = re.compile(r"^[1-9][0-9]{5}$")
FIELDS = ("name", "state", "address", "city", "pincode", "pt_registration", "lwf_registration", "esi_code",
          "se_registration")


class LocationService:
    def __init__(self, payroll: PayrollService):
        self.payroll = payroll
        self.repo = payroll.repo

    def ensure_head_office(self, client_id: str) -> ClientLocation:
        """Every client has a head office; made from the client's own details the first time it's needed."""
        existing = self.repo.list_locations(client_id)
        head = next((l for l in existing if l.head_office), None)
        if head:
            return head
        client = self.repo.get_client(client_id)
        head = ClientLocation(id=uuid.uuid4().hex, client_id=client_id, name="Head office", state=client.state,
                              pt_registration=client.pt_registration, esi_code="", head_office=True)
        self.repo.save_location(head)
        return head

    def locations(self, client_id: str) -> list[dict]:
        self.ensure_head_office(client_id)
        counts: dict[str, int] = {}
        head = next(l for l in self.repo.list_locations(client_id) if l.head_office)
        for r in self.repo.list_employees(client_id):
            if r.exited_on is None:
                key = r.employee.location_id or head.id
                counts[key] = counts.get(key, 0) + 1
        supported = set(self.payroll.rules.supported_states)
        return [{"location": l, "employees": counts.get(l.id, 0), "rules_ready": l.state in supported}
                for l in self.repo.list_locations(client_id)]

    def save(self, actor: User, client_id: str, data: dict, location_id: str | None = None) -> ClientLocation:
        self.repo.get_client(client_id)
        old = self.repo.get_location(location_id) if location_id else None
        if old and old.client_id != client_id:
            raise ServiceError("This location belongs to another client")
        v = {k: str(data.get(k) or "").strip() for k in FIELDS}
        v["state"] = v["state"].upper()
        v["pt_registration"] = v["pt_registration"].upper()
        errors: dict[str, str] = {}
        if not v["name"]:
            errors["name"] = "Enter a name, e.g. Bengaluru branch"
        elif any(l.name.lower() == v["name"].lower() and l.id != location_id for l in self.repo.list_locations(client_id)):
            errors["name"] = "This client already has a location with this name"
        if v["state"] not in STATE_NAMES:
            errors["state"] = "Choose a state"
        elif v["state"] not in self.payroll.rules.supported_states:
            errors["state"] = (f"No Professional Tax / LWF rules for {STATE_NAMES[v['state']]} yet; "
                               "add them under Tax and rules → Compliance rules first")
        if v["pincode"] and not PINCODE.match(v["pincode"]):
            errors["pincode"] = "Enter a 6-digit PIN code"
        head_office = bool(data.get("head_office", old.head_office if old else False))
        active = bool(data.get("active", True))
        if old and old.head_office and not head_office:
            errors["head_office"] = "Make another location the head office instead"
        if (old and not active and old.active) or (old and old.state != v["state"]):
            working = [r.code for r in self.repo.list_employees(client_id) if r.exited_on is None and
                       (r.employee.location_id == old.id or (old.head_office and not r.employee.location_id))]
            if not active and working:
                errors["active"] = f"{len(working)} employee(s) work here; move them to another location first"
            if not active and old.head_office:
                errors["active"] = "The head office can't be switched off"
        if errors:
            raise ServiceError("Check the highlighted fields", errors=errors)
        loc = ClientLocation(id=old.id if old else uuid.uuid4().hex, client_id=client_id, head_office=head_office,
                             active=active, **v)
        if head_office:  # only one head office
            for other in self.repo.list_locations(client_id):
                if other.head_office and other.id != loc.id:
                    other.head_office = False
                    self.repo.save_location(other)
        self.repo.save_location(loc)
        if old and old.state != loc.state:  # employees there now follow the new state's PT and LWF
            self._restate(client_id, loc)
        self.payroll._audit(actor.email, "location.update" if old else "location.create", f"client/{client_id}",
                            f"{loc.name} ({loc.state})")
        return loc

    def _restate(self, client_id: str, loc: ClientLocation) -> None:
        for r in self.repo.list_employees(client_id):
            here = r.employee.location_id == loc.id or (loc.head_office and not r.employee.location_id)
            if here and r.employee.state != loc.state:
                r.employee.state = loc.state
                self.repo.save_employee(r)

    def resolve(self, client_id: str, location_id: str | None) -> ClientLocation:
        """The location an employee is put at (the head office when none is given)."""
        if not location_id:
            return self.ensure_head_office(client_id)
        try:
            loc = self.repo.get_location(location_id)
        except LookupError:
            raise ServiceError("Choose one of this client's locations", field="location_id") from None
        if loc.client_id != client_id:
            raise ServiceError("Choose one of this client's locations", field="location_id")
        if not loc.active:
            raise ServiceError("This location is switched off", field="location_id")
        return loc

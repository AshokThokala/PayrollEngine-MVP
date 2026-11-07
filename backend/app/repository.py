"""Storage interface and an in-memory implementation.

The service layer only talks to ``Repository``. A PostgreSQL implementation
will follow; the in-memory one backs the tests and local demos.
"""
from __future__ import annotations

from typing import Protocol

from .domain import AuditEvent, Client, EmployeeRecord, Filing, PayrollRun


class NotFound(LookupError):
    pass


class Repository(Protocol):
    def add_client(self, client: Client) -> None: ...
    def get_client(self, client_id: str) -> Client: ...
    def list_clients(self) -> list[Client]: ...

    def save_employee(self, record: EmployeeRecord) -> None: ...
    def get_employee(self, client_id: str, code: str) -> EmployeeRecord: ...
    def list_employees(self, client_id: str) -> list[EmployeeRecord]: ...

    def save_run(self, run: PayrollRun) -> None: ...
    def get_run(self, run_id: str) -> PayrollRun: ...
    def list_runs(self, client_id: str) -> list[PayrollRun]: ...

    def save_filing(self, filing: Filing) -> None: ...
    def get_filing(self, filing_id: str) -> Filing: ...
    def list_filings(self, client_id: str | None = None) -> list[Filing]: ...

    def append_audit(self, event: AuditEvent) -> None: ...
    def audit_log(self) -> list[AuditEvent]: ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}
        self._employees: dict[tuple[str, str], EmployeeRecord] = {}
        self._runs: dict[str, PayrollRun] = {}
        self._filings: dict[str, Filing] = {}
        self._audit: list[AuditEvent] = []

    @staticmethod
    def _get(store: dict, key, what: str):
        try:
            return store[key]
        except KeyError:
            raise NotFound(f"{what} {key!r} not found") from None

    def add_client(self, client: Client) -> None:
        if client.id in self._clients:
            raise ValueError(f"Client {client.id!r} already exists")
        self._clients[client.id] = client

    def get_client(self, client_id: str) -> Client:
        return self._get(self._clients, client_id, "Client")

    def list_clients(self) -> list[Client]:
        return list(self._clients.values())

    def save_employee(self, record: EmployeeRecord) -> None:
        self._employees[(record.client_id, record.code)] = record

    def get_employee(self, client_id: str, code: str) -> EmployeeRecord:
        return self._get(self._employees, (client_id, code), "Employee")

    def list_employees(self, client_id: str) -> list[EmployeeRecord]:
        return [r for (cid, _), r in self._employees.items() if cid == client_id]

    def save_run(self, run: PayrollRun) -> None:
        self._runs[run.id] = run

    def get_run(self, run_id: str) -> PayrollRun:
        return self._get(self._runs, run_id, "Payroll run")

    def list_runs(self, client_id: str) -> list[PayrollRun]:
        runs = [r for r in self._runs.values() if r.client_id == client_id]
        return sorted(runs, key=lambda r: r.period)

    def save_filing(self, filing: Filing) -> None:
        self._filings[filing.id] = filing

    def get_filing(self, filing_id: str) -> Filing:
        return self._get(self._filings, filing_id, "Filing")

    def list_filings(self, client_id: str | None = None) -> list[Filing]:
        items = [f for f in self._filings.values() if client_id in (None, f.client_id)]
        return sorted(items, key=lambda f: (f.due_on, f.client_id, f.kind))

    def append_audit(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def audit_log(self) -> list[AuditEvent]:
        return list(self._audit)

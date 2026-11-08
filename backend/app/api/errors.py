"""Turn validation and business-rule errors into messages that name the field.

Every error response has this shape:

    {"detail": "PAN: Enter 10 characters ...",          # one readable line
     "errors": [{"field": "pan", "label": "PAN", "message": "Enter ..."}]}
"""
from __future__ import annotations

from typing import Any

FIELD_LABELS = {
    # client
    "id": "Client ID",
    "legal_name": "Legal name",
    "state": "State",
    "pan": "PAN",
    "tan": "TAN",
    "pf_code": "PF code",
    "esi_code": "ESI code",
    "pt_registration": "PT registration",
    # employee
    "code": "Employee code",
    "name": "Name",
    "joined_on": "Joined on",
    "components": "Monthly salary",
    "pf_member": "PF member",
    "eps_member": "EPS member",
    "pf_on_full_wages": "PF on full wages",
    "esi_covered": "ESI",
    "pt_applicable": "Professional tax",
    "lwf_applicable": "Labour welfare fund",
    "exit_on": "Exit date",
    # payroll run
    "period": "Pay month",
    "inputs": "Attendance inputs",
    "paid_days": "Paid days",
    "overtime": "Overtime",
    "other_earnings": "Other earnings",
    "other_deductions": "Other deductions",
    # filings
    "status": "Status",
    "challan_ref": "Challan / ack reference",
    "client_id": "Client",
    "overdue_on": "Overdue on",
    # headers
    "x-user": "Acting as",
}

COMPONENT_LABELS = {
    "basic": "Basic",
    "da": "DA",
    "hra": "HRA",
    "conveyance": "Conveyance",
    "special_allowance": "Special allowance",
    "retaining_allowance": "Retaining allowance",
}

# Field-specific wording for format (pattern) errors.
PATTERN_MESSAGES = {
    "id": "Use 2–40 lowercase letters, digits or hyphens, e.g. acme-textiles",
}

# Plain-English wording for common Pydantic error types.
TYPE_MESSAGES = {
    "missing": "This field is required",
    "string_too_short": "This field is required",
    "decimal_parsing": "Enter a number",
    "float_parsing": "Enter a number",
    "int_parsing": "Enter a whole number",
    "bool_parsing": "Choose yes or no",
    "bool_type": "Choose yes or no",
    "date_parsing": "Enter a date as YYYY-MM-DD",
    "date_from_datetime_parsing": "Enter a date as YYYY-MM-DD",
    "date_type": "Enter a date as YYYY-MM-DD",
    "dict_type": "Enter the values as name–amount pairs",
    "too_short": "Enter at least one amount",
}


def label_for(loc: list[Any]) -> tuple[str, str]:
    """Map a Pydantic location like ['body', 'inputs', 'E1', 'paid_days'] to (field, label)."""
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    if not parts:
        return "", "Request"
    field = parts[0]
    label = FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
    if field == "components" and len(parts) > 1:
        label = f"{label} – {COMPONENT_LABELS.get(parts[1], parts[1])}"
    elif field == "inputs" and len(parts) > 2:
        inner = FIELD_LABELS.get(parts[2], parts[2])
        label = f"{inner} ({parts[1]})"
        field = f"inputs.{parts[1]}.{parts[2]}"
    elif len(parts) > 1 and field not in ("components", "inputs"):
        field = ".".join(parts)
    return field, label


def message_for(error: dict) -> str:
    kind = error.get("type", "")
    loc = error.get("loc", [])
    leaf = str(loc[-1]) if loc else ""
    if kind == "string_pattern_mismatch":
        return PATTERN_MESSAGES.get(leaf, "Check the format")
    if kind in ("greater_than_equal", "greater_than"):
        return f"Must be at least {error.get('ctx', {}).get('ge', error.get('ctx', {}).get('gt', 0))}"
    if kind in TYPE_MESSAGES:
        return TYPE_MESSAGES[kind]
    msg = error.get("msg", "Invalid value")
    return msg.removeprefix("Value error, ")


def field_error(field: str, label: str, message: str) -> dict:
    return {"field": field, "label": label, "message": message}


def body(errors: list[dict]) -> dict:
    detail = "; ".join(f"{e['label']}: {e['message']}" if e["label"] else e["message"]
                       for e in errors)
    return {"detail": detail, "errors": errors}


def from_validation(raw_errors: list[dict]) -> dict:
    errors = []
    for err in raw_errors:
        field, label = label_for(list(err.get("loc", [])))
        errors.append(field_error(field, label, message_for(err)))
    return body(errors)


def from_service(message: str, field: str | None) -> dict:
    if not field:
        return body([field_error("", "", message)])
    return body([field_error(field, FIELD_LABELS.get(field, field), message)])

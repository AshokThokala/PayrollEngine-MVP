"""Error messages name the field (no FastAPI needed for these)."""
from decimal import Decimal

from app.api import errors


def test_client_id_pattern_names_the_field():
    out = errors.from_validation([{"type": "string_pattern_mismatch", "loc": ("body", "id"),
                                   "msg": "String should match pattern '^[a-z0-9-]{2,40}$'"}])
    assert out["errors"] == [{"field": "id", "label": "Client ID",
                              "message": "Use 2–40 lowercase letters, digits or hyphens, e.g. acme-textiles"}]
    assert out["detail"].startswith("Client ID: Use 2–40")


def test_missing_and_multiple_fields():
    out = errors.from_validation([
        {"type": "missing", "loc": ("body", "legal_name"), "msg": "Field required"},
        {"type": "missing", "loc": ("header", "authorization"), "msg": "Field required"},
    ])
    assert out["detail"] == "Legal name: This field is required; Login: This field is required"


def test_salary_component_and_attendance_labels():
    out = errors.from_validation([
        {"type": "greater_than_equal", "loc": ("body", "components", "hra"), "msg": "x", "ctx": {"ge": Decimal(0)}},
        {"type": "decimal_parsing", "loc": ("body", "inputs", "E1", "paid_days"), "msg": "x"},
        {"type": "date_parsing", "loc": ("body", "joined_on"), "msg": "x"},
    ])
    labels = [(e["field"], e["label"], e["message"]) for e in out["errors"]]
    assert labels == [
        ("components", "Monthly salary – HRA", "Must be at least 0"),
        ("inputs.E1.paid_days", "Paid days (E1)", "Enter a number"),
        ("joined_on", "Joined on", "Enter a date as YYYY-MM-DD"),
    ]


def test_service_errors_with_and_without_field():
    assert errors.from_service("Enter the challan or acknowledgement reference", "challan_ref")["detail"] == \
        "Challan / ack reference: Enter the challan or acknowledgement reference"
    assert errors.from_service("Maker-checker: the preparer cannot approve their own run", None)["detail"] == \
        "Maker-checker: the preparer cannot approve their own run"

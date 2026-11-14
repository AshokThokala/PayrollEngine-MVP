-- 009: master list of deduction types, and standing deductions per employee.

CREATE TABLE deduction_types (
    code           TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL CHECK (category IN ('statutory', 'voluntary', 'recovery')),
    calc           TEXT NOT NULL CHECK (calc IN ('statutory', 'fixed', 'percent_basic', 'percent_gross')),
    payslip_label  TEXT NOT NULL DEFAULT '',
    default_value  NUMERIC(12, 2),
    max_amount     NUMERIC(12, 2),
    tax_section    TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    system         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE employee_deductions (
    id             TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES clients(id),
    employee_code  TEXT NOT NULL,
    deduction_code TEXT NOT NULL REFERENCES deduction_types(code),
    value          NUMERIC(12, 2) NOT NULL,
    start_month    DATE NOT NULL,
    end_month      DATE,
    note           TEXT NOT NULL DEFAULT '',
    created_by     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX ix_employee_deductions_emp ON employee_deductions (client_id, employee_code);

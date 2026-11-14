-- 012: hourly employees and monthly time sheets.

ALTER TABLE employees ADD COLUMN pay_type TEXT NOT NULL DEFAULT 'salaried';
ALTER TABLE employees ADD COLUMN hourly_rate NUMERIC(12, 2) NOT NULL DEFAULT 0;

CREATE TABLE timesheets (
    client_id      TEXT NOT NULL REFERENCES clients(id),
    employee_code  TEXT NOT NULL,
    month          DATE NOT NULL,
    days           TEXT NOT NULL,            -- JSON: {"1": {"status": "P", "hours": 8, "ot": 0}, ...}
    status         TEXT NOT NULL CHECK (status IN ('draft', 'approved')),
    note           TEXT NOT NULL DEFAULT '',
    updated_by     TEXT NOT NULL DEFAULT '',
    approved_by    TEXT,
    PRIMARY KEY (client_id, employee_code, month)
);

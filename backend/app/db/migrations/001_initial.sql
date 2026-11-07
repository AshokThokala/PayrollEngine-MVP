-- 001: core tables for the payroll + compliance MVP.
-- Written to run on PostgreSQL (production) and SQLite (fast local tests).
-- {serial_pk} is replaced by the migration runner per database.

CREATE TABLE clients (
    id               TEXT PRIMARY KEY,
    legal_name       TEXT NOT NULL,
    state            CHAR(2) NOT NULL,
    pan              TEXT NOT NULL DEFAULT '',
    tan              TEXT NOT NULL DEFAULT '',
    pf_code          TEXT NOT NULL DEFAULT '',
    esi_code         TEXT NOT NULL DEFAULT '',
    pt_registration  TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE employees (
    client_id         TEXT NOT NULL REFERENCES clients(id),
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    state             CHAR(2) NOT NULL,
    pf_member         BOOLEAN NOT NULL DEFAULT TRUE,
    eps_member        BOOLEAN NOT NULL DEFAULT TRUE,
    pf_on_full_wages  BOOLEAN NOT NULL DEFAULT FALSE,
    esi_covered       BOOLEAN,               -- NULL = decide from wages
    pt_applicable     BOOLEAN NOT NULL DEFAULT TRUE,
    lwf_applicable    BOOLEAN NOT NULL DEFAULT TRUE,
    tax_regime        TEXT NOT NULL DEFAULT 'new' CHECK (tax_regime IN ('new', 'old')),
    joined_on         DATE NOT NULL,
    exited_on         DATE,
    PRIMARY KEY (client_id, code),
    CHECK (exited_on IS NULL OR exited_on >= joined_on)
);

-- Salary history: every change is a new version; the highest version is current.
CREATE TABLE salary_components (
    client_id      TEXT NOT NULL,
    employee_code  TEXT NOT NULL,
    version        INTEGER NOT NULL,
    component      TEXT NOT NULL,
    amount         NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (client_id, employee_code, version, component),
    FOREIGN KEY (client_id, employee_code) REFERENCES employees(client_id, code)
);

CREATE TABLE payroll_runs (
    id           TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL REFERENCES clients(id),
    period       DATE NOT NULL,             -- last day of the pay month
    status       TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'locked')),
    prepared_by  TEXT NOT NULL,
    approved_by  TEXT,
    locked_at    TIMESTAMPTZ,
    UNIQUE (client_id, period)
);

CREATE TABLE run_flags (
    run_id   TEXT NOT NULL REFERENCES payroll_runs(id),
    seq      INTEGER NOT NULL,
    message  TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE payslips (
    run_id           TEXT NOT NULL REFERENCES payroll_runs(id),
    employee_code    TEXT NOT NULL,
    period           DATE NOT NULL,
    statutory_wages  NUMERIC(12, 2) NOT NULL,
    gross            NUMERIC(12, 2) NOT NULL,  -- stored for reporting; lines are the source
    total_deductions NUMERIC(12, 2) NOT NULL,
    net_pay          NUMERIC(12, 2) NOT NULL,
    employer_cost    NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (run_id, employee_code)
);

CREATE TABLE payslip_lines (
    run_id         TEXT NOT NULL,
    employee_code  TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('earning', 'deduction', 'employer')),
    seq            INTEGER NOT NULL,
    code           TEXT NOT NULL,
    label          TEXT NOT NULL,
    amount         NUMERIC(12, 2) NOT NULL,
    rule_version   TEXT,                      -- e.g. central.pf@2026-09-17
    PRIMARY KEY (run_id, employee_code, kind, seq),
    FOREIGN KEY (run_id, employee_code) REFERENCES payslips(run_id, employee_code)
);

CREATE TABLE payslip_warnings (
    run_id         TEXT NOT NULL,
    employee_code  TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    message        TEXT NOT NULL,
    PRIMARY KEY (run_id, employee_code, seq),
    FOREIGN KEY (run_id, employee_code) REFERENCES payslips(run_id, employee_code)
);

CREATE TABLE filings (
    id           TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL REFERENCES clients(id),
    kind         TEXT NOT NULL,
    period       TEXT NOT NULL,
    due_on       DATE NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'filed')),
    amount       NUMERIC(12, 2),
    challan_ref  TEXT
);

CREATE TABLE audit_events (
    id         {serial_pk},
    at         TIMESTAMPTZ NOT NULL,
    user_name  TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX ix_runs_client_period ON payroll_runs (client_id, period);
CREATE INDEX ix_filings_due ON filings (due_on, status);
CREATE INDEX ix_filings_client ON filings (client_id);
CREATE INDEX ix_audit_entity ON audit_events (entity);

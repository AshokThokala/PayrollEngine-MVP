-- 011: pay codes (earnings) at master and client level. Employee amounts live in the salary structure.

CREATE TABLE pay_codes (
    code           TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('fixed', 'variable')),
    tax            TEXT NOT NULL CHECK (tax IN ('taxable', 'partly_exempt', 'exempt')),
    calc           TEXT NOT NULL CHECK (calc IN ('fixed', 'percent_basic')),
    default_value  NUMERIC(12, 2),
    payslip_label  TEXT NOT NULL DEFAULT '',
    tax_section    TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    core           BOOLEAN NOT NULL DEFAULT FALSE,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    system         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE client_pay_codes (
    client_id      TEXT NOT NULL REFERENCES clients(id),
    pay_code       TEXT NOT NULL REFERENCES pay_codes(code),
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    default_value  NUMERIC(12, 2),
    payslip_label  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (client_id, pay_code)
);

-- 007: what each client pays, and the monthly invoices.

CREATE TABLE billing_plans (
    client_id          TEXT PRIMARY KEY REFERENCES clients(id),
    plan               TEXT NOT NULL CHECK (plan IN ('software', 'managed')),
    rate_per_employee  NUMERIC(12, 2) NOT NULL CHECK (rate_per_employee >= 0),
    minimum_fee        NUMERIC(12, 2) NOT NULL CHECK (minimum_fee >= 0),
    onboarding_fee     NUMERIC(12, 2) NOT NULL CHECK (onboarding_fee >= 0),
    gst_rate           NUMERIC(5, 4) NOT NULL,
    billing_email      TEXT NOT NULL DEFAULT '',
    starts_on          DATE
);

CREATE TABLE invoices (
    id           TEXT PRIMARY KEY,               -- client_id:YYYY-MM
    client_id    TEXT NOT NULL REFERENCES clients(id),
    number       TEXT UNIQUE,                    -- set when issued
    period       DATE NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    lines        TEXT NOT NULL,                  -- JSON list of {description, quantity, rate, amount}
    subtotal     NUMERIC(12, 2) NOT NULL,
    cgst         NUMERIC(12, 2) NOT NULL,
    sgst         NUMERIC(12, 2) NOT NULL,
    igst         NUMERIC(12, 2) NOT NULL,
    total        NUMERIC(12, 2) NOT NULL,
    issue_date   DATE,
    due_date     DATE,
    paid_on      DATE,
    payment_ref  TEXT
);

CREATE INDEX ix_invoices_client_period ON invoices (client_id, period);
CREATE INDEX ix_invoices_status ON invoices (status, due_date);

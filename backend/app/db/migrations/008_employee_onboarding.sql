-- 008: employee invite links and the onboarding profile each employee fills in.

CREATE TABLE invites (
    id             TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES clients(id),
    employee_code  TEXT NOT NULL,
    email          TEXT NOT NULL,
    token_hash     TEXT NOT NULL UNIQUE,      -- SHA-256 of the link token; the token itself is never stored
    created_by     TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    accepted_at    TIMESTAMPTZ,
    revoked        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_invites_employee ON invites (client_id, employee_code);

CREATE TABLE employee_profiles (
    client_id      TEXT NOT NULL REFERENCES clients(id),
    employee_code  TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'returned', 'verified')),
    details        TEXT NOT NULL,             -- JSON: contact, address, UAN, ESI IP, bank name, IFSC
    pan_enc        TEXT,                      -- encrypted (Fernet)
    account_enc    TEXT,                      -- encrypted (Fernet)
    submitted_at   TIMESTAMPTZ,
    verified_by    TEXT,
    verified_at    TIMESTAMPTZ,
    note           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (client_id, employee_code)
);

-- 005: logins. role 'admin' with no client_id = platform admin (service team);
-- 'admin' with a client_id = that client's admin; 'employee' = one employee of one client.

CREATE TABLE users (
    id             TEXT PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,      -- stored lower-case
    name           TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
    password_hash  TEXT NOT NULL,             -- scrypt, never the password
    status         TEXT NOT NULL CHECK (status IN ('active', 'pending', 'disabled')),
    client_id      TEXT REFERENCES clients(id),
    employee_code  TEXT,
    created_at     TIMESTAMPTZ NOT NULL,
    CHECK (role = 'admin' OR (client_id IS NOT NULL AND employee_code IS NOT NULL))
);

CREATE INDEX ix_users_client ON users (client_id);
CREATE UNIQUE INDEX ux_users_employee ON users (client_id, employee_code);

-- 013: client locations (head office, branches, sites) and where each employee works.

CREATE TABLE client_locations (
    id               TEXT PRIMARY KEY,
    client_id        TEXT NOT NULL REFERENCES clients(id),
    name             TEXT NOT NULL,
    state            TEXT NOT NULL,
    address          TEXT NOT NULL DEFAULT '',
    city             TEXT NOT NULL DEFAULT '',
    pincode          TEXT NOT NULL DEFAULT '',
    pt_registration  TEXT NOT NULL DEFAULT '',
    lwf_registration TEXT NOT NULL DEFAULT '',
    esi_code         TEXT NOT NULL DEFAULT '',
    se_registration  TEXT NOT NULL DEFAULT '',
    head_office      BOOLEAN NOT NULL DEFAULT FALSE,
    active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_client_locations_client ON client_locations (client_id);

ALTER TABLE employees ADD COLUMN location_id TEXT;

-- 003: compliance rules move from JSON files into the database.
-- One row per dated version of a rule; parameters (rates, slabs, due dates) are JSON text.

CREATE TABLE statutory_rules (
    id          TEXT PRIMARY KEY,           -- scope:category:valid_from
    scope       TEXT NOT NULL,              -- 'central' or a state code such as 'TG'
    category    TEXT NOT NULL,
    valid_from  DATE NOT NULL,
    valid_to    DATE,                       -- NULL = still in force
    params      TEXT NOT NULL,              -- JSON object
    source      TEXT NOT NULL DEFAULT '',   -- notification / act reference
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (scope, category, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX ix_rules_scope_category ON statutory_rules (scope, category, valid_from);

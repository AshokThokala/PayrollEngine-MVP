-- 002 (PostgreSQL only): the audit log is append-only.
-- Any UPDATE or DELETE on audit_events raises an error.

CREATE OR REPLACE FUNCTION audit_events_block_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_change();

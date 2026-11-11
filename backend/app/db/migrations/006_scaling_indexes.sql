-- 006: indexes for the queries that grow with clients, months and employees.

-- Locked runs of a client within a date window (TDS year-to-date, variance checks).
CREATE INDEX ix_runs_client_status_period ON payroll_runs (client_id, status, period);
-- One employee's payslips across months (employee portal).
CREATE INDEX ix_payslips_employee ON payslips (employee_code, run_id);
CREATE INDEX ix_payslip_lines_employee ON payslip_lines (employee_code, run_id);
-- Audit log by time.
CREATE INDEX ix_audit_at ON audit_events (at);
-- Filings by client and status (calendar views).
CREATE INDEX ix_filings_client_status ON filings (client_id, status, due_on);

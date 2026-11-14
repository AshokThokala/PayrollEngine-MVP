-- 010: which master deduction types each client uses, with the client's own default, cap and payslip name.

CREATE TABLE client_deductions (
    client_id      TEXT NOT NULL REFERENCES clients(id),
    deduction_code TEXT NOT NULL REFERENCES deduction_types(code),
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    default_value  NUMERIC(12, 2),
    max_amount     NUMERIC(12, 2),
    payslip_label  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (client_id, deduction_code)
);

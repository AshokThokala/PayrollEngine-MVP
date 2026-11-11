-- 004: what each employee has chosen and declared for income tax (TDS on salary).

ALTER TABLE employees ADD COLUMN tax_age_group TEXT NOT NULL DEFAULT 'below_60';
ALTER TABLE employees ADD COLUMN metro_city BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE employees ADD COLUMN parents_senior BOOLEAN NOT NULL DEFAULT FALSE;
-- Annual amounts for the old regime as JSON: rent_paid, sec_80c, sec_80ccd_1b,
-- sec_80d_self, sec_80d_parents, home_loan_interest
ALTER TABLE employees ADD COLUMN tax_declarations TEXT NOT NULL DEFAULT '{}';

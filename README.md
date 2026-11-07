# Payroll + Compliance MVP

Payroll and statutory compliance (PF, ESI, Professional Tax, LWF, TDS) for small Indian firms,
run as software plus a done-for-you service. Launch state: **Telangana**.

## Structure

```
backend/
  app/engine/   pure-Python payroll engine (no web or DB dependencies)
  app/rules/    date-effective statutory rules as JSON (central + per state)
  tests/        pytest suite for the engine
```

Planned next: FastAPI + PostgreSQL API, output files (payslip PDF, bank file, PF ECR),
and a React front end.

## Run the tests

```
cd backend
pip install pytest
python -m pytest
```

## Design rules

- Money is always `Decimal`, never `float`.
- Statutory rates live in `app/rules/*.json` with `valid_from` / `valid_to`; a law change
  is a new entry, not a code change.
- Every statutory payslip line records the rule version it used (e.g. `central.pf@2026-09-17`).

> **Not yet verified for live use.** Rates and dates in `app/rules/` must be signed off by a
> practising Chartered Accountant before processing a real client's payroll.

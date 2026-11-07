# Payroll + Compliance MVP

Payroll and statutory compliance (PF, ESI, Professional Tax, LWF, TDS) for small Indian firms,
run as software plus a done-for-you service. Launch state: **Telangana**.

## Structure

```
backend/
  app/engine/     pure-Python payroll engine (no web or DB dependencies)
  app/rules/      date-effective statutory rules as JSON (central + per state)
  app/services/   payroll workflow (draft -> approved -> locked), compliance calendar
  app/repository.py  storage interface + in-memory implementation
  app/db/         SQL repository (PostgreSQL / SQLite), migrations, migrate CLI
  app/api/        FastAPI routes
  tests/          pytest suite (runs against memory, SQLite and PostgreSQL)
```

Planned next: output files (payslip PDF, bank file, PF ECR) and a React front end.

## Run locally

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                       # engine, service and API tests
uvicorn app.api.main:app --reload      # API docs at http://localhost:8000/docs
```

Every write request needs an `X-User` header (placeholder until real login).
A run must be approved by a different user from the one who prepared it.

## Local PostgreSQL

Without `DATABASE_URL` the API keeps data in memory. To keep data between restarts:

**Option A - Docker** (from the repo root):
```
docker compose up -d          # Postgres 16 on localhost:5432, databases payroll + payroll_test
```

**Option B - installed Postgres** (postgresql.org installer, Postgres.app or Homebrew):
```
psql -U postgres -c "CREATE USER payroll WITH PASSWORD 'payroll';"
psql -U postgres -c "CREATE DATABASE payroll OWNER payroll;"
psql -U postgres -c "CREATE DATABASE payroll_test OWNER payroll;"
```

Then, from `backend/` with the virtual environment active:
```
export DATABASE_URL=postgresql://payroll:payroll@localhost:5432/payroll
# Windows PowerShell: $env:DATABASE_URL="postgresql://payroll:payroll@localhost:5432/payroll"
python -m app.db migrate                 # creates all tables
python -m uvicorn app.api.main:app --reload
```
The API also applies pending migrations on start-up.

Run the test suite against Postgres too (the test database is wiped each run):
```
export TEST_DATABASE_URL=postgresql://payroll:payroll@localhost:5432/payroll_test
python -m pytest
```

### Tables

| Table | Holds |
| --- | --- |
| `clients` | Client firms: PAN, TAN, PF/ESI codes, state |
| `employees` | Employee master and statutory flags |
| `salary_components` | Versioned salary history (highest version = current) |
| `payroll_runs` | One run per client per month, with status and approver |
| `run_flags` | Review flags on a run |
| `payslips` | Totals per employee per run |
| `payslip_lines` | Every earning, deduction and employer line with its rule version |
| `payslip_warnings` | Warnings per payslip |
| `filings` | Compliance calendar: due dates, status, challan reference |
| `audit_events` | Append-only audit log (UPDATE/DELETE blocked on Postgres) |
| `schema_migrations` | Applied migrations |

## Design rules

- Money is always `Decimal`, never `float`.
- Statutory rates live in `app/rules/*.json` with `valid_from` / `valid_to`; a law change
  is a new entry, not a code change.
- Every statutory payslip line records the rule version it used (e.g. `central.pf@2026-09-17`).

> **Not yet verified for live use.** Rates and dates in `app/rules/` must be signed off by a
> practising Chartered Accountant before processing a real client's payroll.

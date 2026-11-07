# Payroll + Compliance MVP

Payroll and statutory compliance (PF, ESI, Professional Tax, LWF, TDS) for small Indian firms,
run as software plus a done-for-you service. Launch state: **Telangana**.

## Run the whole app with Docker

Needs Docker Desktop. From the repo root:
```
docker compose up -d --build
```
Open **http://localhost:8080**. That starts three containers:

| Container | What | Port |
| --- | --- | --- |
| `web` | React UI served by nginx; forwards `/api/*` to the API | 8080 |
| `api` | FastAPI; creates/updates tables on start-up | 8000 (docs at `/docs`) |
| `db` | PostgreSQL 16; data kept in the `pgdata` volume | 5432 |

Useful commands:
```
docker compose ps                 # what is running
docker compose logs -f api        # API logs
docker compose up -d --build      # rebuild after pulling new code
docker compose down               # stop (data is kept)
docker compose down -v            # stop and DELETE all data
```

### Using the UI
1. **Clients** - add a client firm (state: Telangana).
2. **Employees** - add employees with their monthly salary split; you are warned if basic + DA is under 50%.
3. **Payroll runs** - pick a month and *Calculate draft*. Open payslips to see every line.
   To approve, change **Acting as** (top right) to a different name - the preparer cannot approve.
   Then *Lock run* to freeze it.
4. **Compliance calendar** - locking creates PF, ESI, TDS, PT, LWF and Form 24Q items with due dates.
   Enter the challan reference and mark them paid or filed. Overdue items are highlighted.

"Acting as" is a placeholder for real login; it is recorded in the audit log.

## Frontend development (without Docker)
```
cd frontend
npm install
npm run dev        # http://localhost:5173, forwards /api to http://localhost:8000
```
Run the API separately (see below).

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
frontend/         React (Vite) UI, nginx config, Dockerfile
docker-compose.yml  db + api + web
```

Planned next: output files (payslip PDF, bank file, PF ECR) and real login.

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

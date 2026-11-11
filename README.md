# ClearPay4U — zero-penalty payroll

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

### Logging in
| Who | How they get in | What they can do |
| --- | --- | --- |
| **Platform admin** (your service team) | First one is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (Docker default: `admin@clearpay4u.local` / `ChangeMe123` - change it) | Every client, compliance rules, all users |
| **Client admin** | *Sign up a business* on the login page | Their own client: employees, payroll runs, filings, approving employee accounts |
| **Employee** | *I'm an employee* with the client ID and their employee code; their employer approves the account | Their own profile, final (locked) payslips and tax declarations |

Passwords are hashed with scrypt; logins last 12 hours. Set `SECRET_KEY` (see `backend/.env.example`).
A payroll run must be approved by a different admin from the one who calculated it.

### Using the UI
1. **Clients** - add a client firm. Only states that have compliance rules can be chosen.
2. **Employees** - add employees with their monthly salary split; you are warned if basic + DA is under 50%.
3. **Payroll runs** - pick a month and *Calculate draft*. Open payslips to see every line.
   A different admin approves it, then *Lock run* freezes it and employees can see their payslips.
4. **Compliance calendar** - locking creates PF, ESI, TDS, PT, LWF and Form 24Q items with due dates.
   Enter the challan reference and mark them paid or filed. Overdue items are highlighted.
5. **Compliance rules** - every statutory rule with its dated versions. *Add rule version* to change a rate,
   slab or due date from a given date (the previous version ends the day before), or add Professional Tax /
   LWF rules for a new state so clients can be created there. *Edit* on any version corrects its values or
   source (dates stay; recorded in the audit log).
6. **Income tax** - on Employees, *Edit* in the Tax column sets the regime (new is default, or old), age group
   and old-regime declarations (rent, 80C, 80CCD(1B), 80D, home loan interest). Monthly TDS projects the year,
   applies slabs, rebate, surcharge with marginal relief and 4% cess, and spreads the rest over the months left.

### Income tax coverage (Tax Year 2026-27, Income-tax Act 2025 s.392)
| | New regime (default) | Old regime |
| --- | --- | --- |
| Slabs | 0 / 5 / 10 / 15 / 20 / 25 / 30% | By age: below 60, 60-79, 80+ |
| Standard deduction | ₹75,000 | ₹50,000 |
| Rebate | Up to ₹60,000 (income ≤ ₹12 lakh) with marginal relief | Up to ₹12,500 (income ≤ ₹5 lakh) |
| Surcharge | 10 / 15 / 25% (cap) with marginal relief | 10 / 15 / 25 / 37% with marginal relief |
| Deductions | - | Professional tax (≤ ₹2,500), HRA, 80C incl. employee PF, 80CCD(1B), 80D, home loan interest |
| Cess | 4% | 4% |

Not yet covered: perquisites, employer NPS (80CCD(2)), income from other sources or a previous employer.


## Theme
"Clear books": **navy** `#0f2a3a` for trust (sidebar, headers), **emerald** `#0b7a63` for primary actions and
"paid / compliant" states, and a small **saffron** `#e8a317` accent (logo, active item, portal header line).
Headings use **Poppins** (Indian Type Foundry; also covers Devanagari), body text and numbers use **Inter** with
tabular figures so rupee amounts line up. Fonts are bundled with the app (no Google Fonts requests).
All colours are CSS variables at the top of `frontend/src/styles.css`; every text/background pair meets WCAG AA.

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

Every API call except login, sign-up and `/rules/states` needs `Authorization: Bearer <token>` from `POST /auth/login`.
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
| `statutory_rules` | Compliance rules: one row per dated version (scope, category, valid_from/to, JSON values, source) |
| `schema_migrations` | Applied migrations |

## Design rules

- Money is always `Decimal`, never `float`.
- Statutory rules live in the `statutory_rules` table with `valid_from` / `valid_to`; a law change
  is a new version added on the Compliance rules page, not a code change. `app/rules/*.json` holds the
  default rules loaded into an empty table on first start. `app/rule_schemas.py` defines the fields
  each rule type must have and validates new versions.
- Every statutory payslip line records the rule version it used (e.g. `central.pf@2026-09-17`).

> **Not yet verified for live use.** Rates and dates in `app/rules/` must be signed off by a
> practising Chartered Accountant before processing a real client's payroll.

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

### Working in the app
- **Employee search** (top of every admin page; press `/` or Ctrl/⌘+K): finds employees by name or code, across every
  client for platform admins (client admins: their own employees). Arrow keys and Enter pick a result, which switches
  to the employee's client and opens their record. Clients are found with the client switcher.
- **Switch clients** with the client button at the top right (search by name or ID). Client admins see only their company.
- **Click a client or employee row** to open its details and edit them; *+ Add client* / *+ Add employee* open the add form.
- **View as employee** (on an employee's details) opens the employee portal exactly as that employee sees it,
  read-only, for one hour, with a *Back to admin* button. Every use is recorded in the audit log; it works even if
  the employee has no login yet.
- **Reports**: salary register, statutory dues by month, payroll cost trend (with chart), compliance status and
  income tax summary - each with totals and *Download CSV*.
- **Employee onboarding**: invite → register → onboard → verify. Pick an employee, enter their email and
  *Make invite link*; copy the link (it works once, for 7 days; a new link cancels the old one) and send it yourself -
  there is no email service yet. The employee opens `/invite/<token>`, sets a password and is logged in straight away.
  In the portal they fill in *Joining details* in steps (contact and emergency contact; PAN, UAN, ESI IP; salary bank
  account and IFSC), then submit. The admin checks the details and *Verifies* them or *Sends back* with a note.
  PAN and account numbers are encrypted at rest (Fernet; key from `FIELD_ENCRYPTION_KEY`, or derived from
  `SECRET_KEY` - keep it stable). Only a SHA-256 hash of each invite token is stored.
- **Tax rules** (all admins; editing for platform admins): income tax for the Tax Year in force on any date -
  new-regime and old-regime slabs (old by age group), standard deduction, rebate, surcharge and cess, old-regime
  deduction limits (80C, 80CCD(1B), 80D, home loan, HRA formula), TDS deposit and Form 24Q due dates, and the version
  history. *Compare regimes* works out a year's tax under both regimes step by step (deductions, each slab, rebate,
  surcharge, cess, monthly TDS) and shows which is lower. *Change* opens that rule on the Compliance rules page.
- **Client onboarding**: a 7-step checklist per client (company details, statutory registrations, client admin
  login, billing plan, employees, salary structures, first locked payroll) with a progress bar and a *Go* button to
  the page that finishes each step. Platform admins also see every client, least complete first.
- **Billing** (platform admin): set the plan - *Software only* (₹60 per employee a month) or *Managed payroll and
  compliance* (₹150 per employee, ₹5,000 monthly minimum, ₹15,000 one-time onboarding) - with any custom rate.
  *Generate invoice* for a month with a locked payroll run (headcount = employees paid that month), check the draft,
  *Issue invoice* (number CP4U/FY/0001, due in 15 days), then *Mark paid* with the UTR. GST is 18%: CGST + SGST
  when the client is in the provider's state (`PROVIDER_STATE`, default TG), otherwise IGST. *Print / save PDF*
  prints just the invoice. Client admins see their plan and issued invoices; drafts stay internal.

### Using the UI
1. **Clients** - add a client firm. Only states that have compliance rules can be chosen.
2. **Employees** - add employees with their monthly salary split; you are warned if basic + DA is under 50%.
3. **Payroll runs** - pick a month and *Calculate draft*. Open payslips to see every line.
   A different admin approves it, then *Lock run* freezes it and employees can see their payslips.
4. **Compliance calendar** - locking creates PF, ESI, TDS, PT, LWF and Form 24Q items with due dates.
   Enter the challan reference and mark them paid or filed. Overdue items are highlighted.
5. **Compliance rules** - one row per rule (scope, in force since, versions). Click a rule to open it in the editor
   on its version in force: change values or source to correct it, switch to another version with the version tabs, or
   *+ New version* to change it from a later date (the previous version ends the day before). *+ Add rule version*
   adds any rule, including Professional Tax / LWF for a new state so clients can be created there.
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


## Scaling

The app is built so it can grow by adding capacity rather than rewriting:

| Area | What is in place |
| --- | --- |
| Stateless API | Logins are signed tokens, so any worker or container can serve any request. Run several API containers behind a load balancer with the same `SECRET_KEY`. |
| Worker processes | `WEB_CONCURRENCY` uvicorn workers per container (default 2). |
| Database connections | One PostgreSQL connection pool per worker (`DB_POOL_SIZE`, default 10) instead of a new connection per call. Keep workers × pool size × containers below Postgres `max_connections`. |
| Rules cache | Compliance rules are cached per worker for `RULES_CACHE_SECONDS` (default 30); saving a rule clears it at once in that worker. |
| Queries | Run lists use one aggregate query (no payslips loaded); TDS reads only this financial year's locked runs; the employee portal fetches only that employee's payslips; indexes for each of these (migration 006). |
| Responses | Gzip from the API and nginx; built JS/CSS cached for a year (hashed file names), `index.html` never cached. |
| Lists | Filings and users accept `limit` / `offset` (default 500). |

Next steps when volume needs them: a shared cache (e.g. Redis) for rules and sessions, background jobs for
large payroll runs and report exports, read replicas for reporting, and partitioning `audit_events` by month.

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
| `billing_plans` | One billing plan per client: plan, rates, billing email |
| `invoices` | Monthly invoices: lines (JSON), GST split, number, status, payment reference |
| `invites` | Employee invite links: email, token hash, expiry, used/cancelled |
| `employee_profiles` | Joining details per employee; PAN and account number encrypted; draft/submitted/returned/verified |
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

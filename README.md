# Sentinel

Sentinel monitors webpages, explains meaningful changes, and helps you decide what
to do next. It combines a **Next.js and Tailwind CSS dashboard**, a **FastAPI API**,
and a **background worker** with PostgreSQL, pgvector, and Gemini.

Each registered account has its own workspace: sources, findings, profile,
memories, action progress, notifications, and weekly digests are private to that
account. The frontend reads and updates real backend data.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Quick start with Docker](#quick-start-with-docker)
- [Local development](#local-development)
- [Using Sentinel](#using-sentinel)
- [Configuration](#configuration)
- [Authentication and user isolation](#authentication-and-user-isolation)
- [Monitoring and intelligence workflow](#monitoring-and-intelligence-workflow)
- [Memory, recommendations, and actions](#memory-recommendations-and-actions)
- [Email notifications and weekly digests](#email-notifications-and-weekly-digests)
- [API reference](#api-reference)
- [Database and migrations](#database-and-migrations)
- [Tests and verification](#tests-and-verification)
- [Troubleshooting](#troubleshooting)
- [Deployment notes](#deployment-notes)
- [Project structure](#project-structure)
- [Current limitations](#current-limitations)

## Features

| Area | What Sentinel provides |
| --- | --- |
| Accounts | Signup, login, logout, and persistent sessions |
| Private workspaces | Ownership checks on API reads and mutations; account-specific worker context |
| Sources | Add public HTTP/HTTPS webpages, set a check interval, pause/resume, and queue manual checks |
| Monitoring | Text extraction, snapshots, content hashes, diffs, retries, and Chromium fallback for selected JavaScript-rendered pages |
| Intelligence | Semantic change summaries, relevance scores, recommendations, and evidence-backed investigations |
| Memory | Account-specific profile memories, findings, preferences, interactions, decisions, and outcomes |
| Actions | Suggested steps, supporting evidence, available/missing resources, deadlines, and progress updates |
| Alerts | Durable email outbox, urgency handling, cooldowns, and delivery retries |
| Digests | Account-specific weekly reports built from stored findings and unfinished actions |
| Dashboard | Overview, intelligence filters, sources, actions, alerts, digests, and profile settings |

## Architecture

```mermaid
flowchart LR
    Browser[Browser] --> Next[Next.js :3000]
    Next -->|Same-origin /api proxy| API[FastAPI :8000]
    API --> DB[(PostgreSQL + pgvector)]
    Worker[Background worker] --> DB
    Worker --> Websites[Monitored webpages]
    Worker --> Gemini[Gemini analysis and embeddings]
    API --> Gemini
    Worker --> SMTP[SMTP email delivery]
    API --> SMTP
```

The browser calls `/api/*` on the frontend. A Next.js route handler forwards allowed
requests to FastAPI, including session cookies and CSRF headers. `BACKEND_URL` is
server-only. Browser requests do not need to cross directly to the API origin.

FastAPI validates requests, authenticates accounts, enforces ownership, and queues
watch checks. Long-running monitoring work runs in a **separate worker process**,
not inside an API request. PostgreSQL stores durable jobs and results; LangGraph
coordinates the steps of an individual check.

Database schema setup happens through **Alembic migrations**, not API startup.
The worker must be running for queued checks and scheduled tasks to execute.

## Technology stack

| Component | Technology |
| --- | --- |
| Frontend | Next.js 16 App Router, React 19, TypeScript |
| Styling and icons | Tailwind CSS 4, Lucide React |
| API | FastAPI, Uvicorn, Pydantic |
| Database | PostgreSQL 17, pgvector, SQLAlchemy, psycopg |
| Migrations | Alembic |
| Workflow | LangGraph |
| Scheduling | APScheduler |
| Fetching | HTTPX, Beautiful Soup, Playwright/Chromium |
| AI | Google Gen AI SDK for Gemini generation and embeddings |
| Email | SMTP via Python's standard library |
| Verification | Python unittest, frontend TypeScript checks, Next.js production build |

The Docker images use **Python 3.12** and **Node.js 24**. These are the recommended
starting versions for a fresh local setup. Exact frontend dependency versions are
recorded in `frontend/package-lock.json`; backend constraints are in
`requirements.txt`.

## Quick start with Docker

You need Docker with Compose and a Gemini API key. On macOS, start Docker Desktop
before running Docker commands. Run the following from the repository root.

### 1. Configure the environment

If you do not already have a root `.env`, create one:

```sh
cp .env.example .env
```

Edit `.env` and replace `GEMINI_API_KEY` with your key. Keep your existing `.env`
when upgrading an installation. The template contains local development database
credentials matching Compose.

### 2. Start the complete application

```sh
docker compose up --build -d
```

Compose starts PostgreSQL, waits for database health, runs migrations, and starts
the API, frontend, and worker. Its database URL override uses `postgres:5432`
inside containers; the host machine uses `localhost:5430`.

### 3. Open Sentinel

| Service | Address |
| --- | --- |
| Dashboard, signup, and login | http://localhost:3000 |
| FastAPI interactive documentation | http://localhost:8000/docs |
| API health | http://localhost:8000/health |
| PostgreSQL from the host | `localhost:5430` |

Create an account, complete your profile, and add your first source.

### 4. Inspect or stop services

```sh
# Service status
docker compose ps

# API and worker logs
docker compose logs -f api worker

# Frontend logs
docker compose logs -f frontend

# Stop services; keep containers and database data
docker compose stop

# Resume stopped services
docker compose start
```

`docker compose down` removes the Compose containers and network while retaining
the named database volume. Adding `--volumes` deletes that volume and its data.

## Local development

Use Docker for PostgreSQL and run the API, worker, and frontend on your machine.
Run all commands from the repository root. Do not run the full Compose application
at the same time as local API/frontend processes on the same ports.

### 1. Install dependencies

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
npm --prefix frontend ci
```

On Linux, Playwright may also need operating-system packages; its
`install --with-deps chromium` option installs those dependencies. The backend
Dockerfile already installs Chromium and its system dependencies.

Create `.env` from [.env.example](.env.example) if it does not exist and set your
Gemini key. The local database URL should be:

```dotenv
DATABASE_URL=postgresql+psycopg://sentinel_user:sentinel_pass@localhost:5430/sentinel
```

### 2. Start the database and apply migrations

```sh
docker compose up -d --wait postgres
.venv/bin/alembic upgrade head
```

### 3. Start the API — terminal 1

```sh
.venv/bin/uvicorn app.main:app --reload
```

### 4. Start the worker — terminal 2

```sh
.venv/bin/python -m app.worker
```

### 5. Start the frontend — terminal 3

```sh
npm --prefix frontend run dev
```

Open **http://localhost:3000**. The development script uses Webpack and supports
Next.js hot reload.

The frontend defaults to `http://127.0.0.1:8000` for backend requests. To change
that address, create its local environment file:

```sh
cp frontend/.env.example frontend/.env.local
```

Then edit `BACKEND_URL` and restart the frontend.

### Stop local development

Press **Ctrl+C** in each API, worker, and frontend terminal, then stop PostgreSQL:

```sh
docker compose stop postgres
```

On your next run, start PostgreSQL again before applying migrations or accessing
database-backed API routes.

## Using Sentinel

1. **Create an account.** Signup also signs you in. Accounts begin with an empty,
   private workspace.
2. **Fill in your profile.** Add skills, interests, preferred roles, locations,
   categories, degree, salary range, and available resources. The dashboard uses
   comma-separated text for list fields.
3. **Add a source.** Give it a name, public webpage URL, category, and check interval
   between 1 and 1,440 minutes. Categories are free text, such as `jobs` or
   `scholarships`.
4. **Let the first check complete.** The first successful fetch establishes a
   baseline snapshot. It does not produce a change finding.
5. **Review later changes.** Meaningful updates appear in Intelligence with
   summaries, relevance, recommendations, and available evidence.
6. **Work through next steps.** Mark actions pending, in progress, or completed.
7. **Review alerts and digests.** Email delivery requires SMTP configuration;
   stored notifications and reports remain available in the dashboard.

A source can be paused to stop future scheduled checks. A check that was already
queued or running may still complete. **Check now** queues work and returns a job
ID; it does not synchronously fetch or analyze the page.

## Configuration

The backend reads settings from environment variables and the root `.env`.
Frontend environment variables belong in `frontend/.env.local` for local
execution, or in the frontend container environment.

### Required and connection settings

| Variable | Default / requirement | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Required | SQLAlchemy PostgreSQL URL using `postgresql+psycopg://` |
| `GEMINI_API_KEY` | Required | Gemini API credential; use a real key for AI features |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Semantic analysis and investigation model |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Memory embedding model; must support 768 dimensions |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Frontend server's API destination; Compose uses `http://api:8000` |
| `FRONTEND_URL` | `http://localhost:3000` | Destination for the API's `/control-center` redirect |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Exact allowed browser origins, comma-separated without spaces or trailing slashes |
| `AUTH_COOKIE_SECURE` | `false` | Set to `true` for HTTPS deployment |

### Intelligence and worker settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `INVESTIGATION_THRESHOLD` | `70` | Relevance threshold for deeper investigation, subject to workflow routing |
| `CHECK_JOB_MAX_ATTEMPTS` | `4` | Maximum job attempts |
| `WORKER_POLL_SECONDS` | `2` | Interval between queue polls |
| `WORKER_STALE_MINUTES` | `30` | Age threshold for recovering abandoned running jobs |
| `WEBSITE_MIN_INTERVAL_SECONDS` | `2.0` | Shared request interval per website host |
| `GEMINI_MIN_INTERVAL_SECONDS` | `1.0` | Shared Gemini request interval |
| `MAX_RATE_WAIT_SECONDS` | `10.0` | Maximum wait before a rate-limited task is deferred |
| `HTTP_TIMEOUT_SECONDS` | `20.0` | HTTP request timeout |
| `HTTP_MAX_BYTES` | `2000000` | Response body limit on the HTTP fetch path |
| `HTTP_RETRY_ATTEMPTS` | `3` | HTTP fetch attempts |
| `BROWSER_TIMEOUT_MS` | `15000` | Chromium navigation timeout |
| `GEMINI_TIMEOUT_MS` | `30000` | Gemini request timeout |

### SMTP and reporting settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | Unset | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | Unset | Optional SMTP username |
| `SMTP_PASSWORD` | Unset | Optional SMTP password |
| `SMTP_FROM` | Unset | Sender email address |
| `SMTP_STARTTLS` | `true` | Enable STARTTLS |
| `NOTIFICATION_TIMEZONE` | `Asia/Karachi` | Deadline and weekly digest scheduling timezone |
| `NOTIFICATION_COOLDOWN_MINUTES` | `180` | Suppress repeated nonurgent emails from the same source during this interval |

SMTP delivery is considered configured when `SMTP_HOST` and `SMTP_FROM` are set.
Recipients come from the owning account's email address. The legacy
`NOTIFICATION_EMAIL_TO` setting is still accepted by configuration but is no longer
used for delivery. SMTP and timezone settings are deployment-wide.

## Authentication and user isolation

### Session behavior

Passwords are stored as salted scrypt hashes. Successful signup/login creates a
random session token in the `sentinel_session` cookie; the database stores its
SHA-256 hash rather than the raw token. Cookies are **HttpOnly**, **SameSite=Lax**,
and expire after **seven days**. `AUTH_COOKIE_SECURE` enables the Secure flag.

Logout deletes the current database session and clears its cookie. Login also
replaces a valid previous session presented by the same browser. Authentication
attempts are limited to **30 per direct API peer per 15 minutes**, shared across
API processes through the database. The Next.js proxy shares that attempt budget;
arbitrary forwarded client IP headers are not trusted.

State-changing requests require `X-Sentinel-CSRF: 1`. FastAPI checks a supplied
Origin against `FRONTEND_ORIGINS`. The frontend proxy additionally requires a
matching browser Origin and Host. The dashboard supplies these headers for you.

### Ownership rules

Sources, profiles, semantic memories, and weekly digests have explicit account
ownership. Findings, snapshots, jobs, investigations, recommendations, actions,
and alerts inherit ownership through their source or finding.

All intelligence API routes require a valid session. Both list queries and
individual-resource mutations enforce ownership. Requests for another account's
IDs return **404**, including checks, job status, action updates, memory feedback,
and digest reads/sends. Ownership is taken from the authenticated account rather
than a client-supplied account ID.

Different accounts can independently use the same source URL, memory source key,
and weekly digest period. The worker loads each source owner's profile and
memories, and outbound delivery addresses that owner's account email.

### Historical shared data

Migration `0005_user_isolation` preserves old shared records with **unassigned
ownership**. They remain in the database but are excluded from account API results,
monitoring, and outbound delivery. Signup never automatically claims old data.

If historical records belong to a known account, an administrator must establish
that ownership and assign the relevant sources, profile, memories, and digests
explicitly. Assigning a source also determines ownership of its existing findings
and dependent records. Downgrading this migration is blocked because removing
ownership would merge private workspaces.

## Monitoring and intelligence workflow

The worker checks for due sources every **30 seconds**, polls queued jobs at
`WORKER_POLL_SECONDS`, and recovers stale jobs every **five minutes**.

A check follows this sequence, with conditional routing:

1. **Monitor:** fetch and extract webpage text; use Chromium fallback when the
   page appears to need JavaScript rendering.
2. **Compare:** hash the content and compare it to the most recent snapshot.
   Unchanged pages finish here; repeated previously analyzed content is deduplicated.
3. **Analyze:** describe the semantic change, its importance, entities, and why
   it matters; persist the snapshot and finding.
4. **Assess relevance:** match the owner's profile and retrieve relevant private
   memories where appropriate.
5. **Recommend:** decide `recommended`, `review`, or `skip`. High-relevance or
   actionable deadline findings may proceed to investigation.
6. **Investigate:** gather source-backed facts and supporting quotes, then update
   the recommendation.
7. **Plan and notify:** build actions for recommended findings and queue eligible
   alerts. Dispatch email when SMTP is configured.
8. **Remember:** store relevant findings as semantic memories for that account.

The graph's execution state is temporary. PostgreSQL keeps durable results, and
completed job results include `workflow_steps` showing which nodes ran.

Jobs have `pending`, `running`, `completed`, or `failed` status. Failures can be
retried with backoff; some permanent errors fail immediately. A database index
prevents multiple pending/running jobs for the same source. Website and Gemini
request budgets are shared across workers.

The `test-change` API queues a simulated content change against an existing
snapshot. It still performs semantic analysis; live investigation and notification
are disabled for that test mode.

## Memory, recommendations, and actions

### Semantic memory

Memories use pgvector with **768-dimensional** Gemini embeddings. Migration setup
creates the vector extension and memory table. Profile updates refresh the account's
profile memory, and relevant findings are remembered with their source URL.

The API supports `preference`, `interaction`, `decision`, and `outcome` memories.
Finding feedback accepts `interested`, `saved`, `applied`, `dismissed`, or
`irrelevant`. Repeated feedback updates the existing memory for that finding.
Similarity searches filter by account before returning results. Profile updates
and memory writes/searches can make Gemini embedding requests.

### Relevance and recommendations

Relevance scores range from 0 to 100 and consider skills, desired roles, interests,
locations, degree, salary preferences, categories, and sufficiently similar prior
feedback. An account without a profile receives an `ignore` relevance priority;
complete your profile to get personalized rankings.

Recommendations include a decision, reasons, priority, and relevance score.
Verified incompatible locations or salary below the minimum can cause a skip.
Failed investigations lead to review rather than an immediate recommendation.
Findings without a saved recommendation receive a computed fallback when listed.

### Action plans

Plans keep supporting source URLs, quotes, and deadlines when verified. Documents
are marked `available` or `missing` according to `available_resources`. Skills
absent from the profile are marked `unconfirmed`, rather than assumed missing.

Action statuses are `pending`, `in_progress`, and `completed`. Creating an already
existing plan returns its existing steps and preserves progress. Plan creation for
an older finding requires a saved `recommended` decision.

## Email notifications and weekly digests

### Immediate alerts

Eligible alerts require the final decision to be `recommended` and the finding's
notification flag. High/critical priority qualifies; a verified deadline within
two calendar days can also qualify. Each email includes the finding, reason,
first action, verified deadline when available, and source URL.

The durable outbox holds one notification per finding. Nonurgent emails are
suppressed when the same source recently sent an alert within the configured
cooldown. Eligible alerts stay pending when SMTP is unconfigured.

The worker dispatches pending notifications every five minutes. SMTP failures
retry with backoff, up to five failed attempts. Delivery states include `pending`,
`sending`, `sent`, `suppressed`, and `failed`.

A row left in `sending` after a crash needs manual review before retry: SMTP may
already have accepted it. Database reservation prevents concurrent dispatch, but
SMTP cannot guarantee exactly-once delivery across every crash scenario.

### Weekly reports

At **09:00 every Monday** in `NOTIFICATION_TIMEZONE`, the worker prepares a report
for the previous completed Monday–Sunday week for each account. Worker startup
also catches up the latest completed week. Each account has one digest per period.

Reports summarize relevant opportunities, verified deadlines within the next
14 days, updates to tracked sources, unfinished actions, deprioritized findings,
and count-based patterns. They use persisted data and **do not call an LLM**.

An empty report is saved with `empty` status. Nonempty reports can be delivered by
SMTP, with retries and the same manual-review requirement for a stuck `sending`
state. Generating a digest through the API may also dispatch it when SMTP is configured.

## API reference

FastAPI serves the endpoints below directly on **port 8000**. In the browser,
prefix intelligence/auth paths with `/api` on **port 3000**; for example,
`/api/watches` proxies to FastAPI's `/watches`.

Interactive schemas are available at `/docs`; the OpenAPI document is
`/openapi.json`. A valid session is required for intelligence endpoints. The
public health endpoint is a lightweight process check, not a database readiness
check.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | API name, status, and version |
| `GET` | `/health` | Process health |
| `GET` | `/control-center` | Redirect to `FRONTEND_URL` |
| `POST` | `/auth/signup` | Create account and session; returns 201 |
| `POST` | `/auth/login` | Sign in |
| `GET` | `/auth/me` | Read current account |
| `POST` | `/auth/logout` | Revoke current session |
| `GET` | `/watches` | List your sources |
| `POST` | `/watches` | Create source and queue its first check |
| `PATCH` | `/watches/{watch_id}` | Pause/resume with `active` |
| `POST` | `/watches/{watch_id}/check` | Queue a check; returns 202 and job ID |
| `GET` | `/watches/check-jobs/{job_id}` | Read owned job status/result |
| `POST` | `/watches/{watch_id}/test-change` | Queue simulated change; needs a prior snapshot |
| `GET` | `/changes` | List findings with relevance, recommendations, investigation, and actions |
| `GET` | `/profile` | Read your profile or empty defaults |
| `PUT` | `/profile` | Replace profile preferences and refresh profile memory |
| `GET` | `/memory` | List recent memories; optional `limit` |
| `GET` | `/memory/search` | Similarity search; required `q`, optional `limit` |
| `POST` | `/memory` | Record a memory, optionally tied to an owned finding |
| `POST` | `/memory/changes/{change_id}/feedback` | Record/update finding feedback |
| `GET` | `/actions/changes/{change_id}` | Read a finding's action plan |
| `POST` | `/actions/changes/{change_id}` | Create a plan for a recommended finding |
| `PATCH` | `/actions/{step_id}` | Update action status |
| `GET` | `/notifications` | List alerts and SMTP configuration availability |
| `POST` | `/notifications/dispatch` | Dispatch your pending eligible alerts |
| `GET` | `/digests/weekly` | List your reports |
| `POST` | `/digests/weekly` | Generate latest completed week; optional `week_start=YYYY-MM-DD` |
| `GET` | `/digests/weekly/{digest_id}` | Read full report |
| `POST` | `/digests/weekly/{digest_id}/send` | Dispatch a pending report |

### Example: authenticate and create a source

These commands call FastAPI directly and save the session cookie to a local file.
Replace the example credentials before use. Treat the cookie file as a credential.

```sh
curl -i -c /tmp/sentinel-cookies.txt \
  http://localhost:8000/auth/signup \
  -H 'Content-Type: application/json' \
  -H 'X-Sentinel-CSRF: 1' \
  --data '{"name":"Your Name","email":"you@example.com","password":"replace-with-a-long-password"}'

curl -b /tmp/sentinel-cookies.txt \
  http://localhost:8000/watches \
  -H 'Content-Type: application/json' \
  -H 'X-Sentinel-CSRF: 1' \
  --data '{"name":"Opportunity board","url":"https://example.com/jobs","category":"jobs","check_interval_minutes":30}'

curl -b /tmp/sentinel-cookies.txt http://localhost:8000/changes
```

For an existing account, use `/auth/login` with `email` and `password`. Passwords
must be between 10 and 128 characters. Direct CLI requests can omit Origin;
browser requests must use a configured origin. Calls through the Next.js proxy
require Origin on mutations.

### Example profile payload

`PUT /profile` replaces the preferences; omitted list fields reset to empty
lists and omitted optional fields reset to null.

```json
{
  "skills": ["Python", "SQL"],
  "degree": "BS Computer Science",
  "interests": ["machine learning"],
  "desired_roles": ["software engineer"],
  "locations": ["Karachi", "remote"],
  "preferred_categories": ["jobs", "scholarships"],
  "available_resources": ["CV", "transcript"],
  "salary_min": 30000,
  "salary_max": 100000
}
```

Salary values represent preferred annual USD amounts and must be positive when
provided. The minimum cannot exceed the maximum.

### Common response codes

| Status | Meaning |
| --- | --- |
| `401` | Missing/expired session or incorrect login credentials |
| `403` | Missing CSRF header or untrusted browser origin |
| `404` | Missing resource or resource outside your account |
| `409` | Duplicate account/source or finding not eligible for plan creation |
| `422` | Invalid request fields |
| `429` | Authentication attempt limit reached |
| `502` | Frontend proxy could not reach the backend or its request timed out |

## Database and migrations

PostgreSQL stores accounts, sessions, profiles, sources, snapshots, findings,
investigations, recommendations, action steps, notifications, weekly digests,
semantic memories, check jobs, authentication attempts, and shared rate limits.

| Revision | Purpose |
| --- | --- |
| `0001_existing_schema` | Baseline tables and pgvector extension |
| `0002_worker_hardening` | Durable job queue, shared request limits, and content deduplication |
| `0003_snapshot_lookup` | Index prior snapshot lookup |
| `0004_auth` | Accounts, revocable sessions, and authentication throttling |
| `0005_user_isolation` | Account ownership and account-specific uniqueness |

```sh
# Apply schema changes
.venv/bin/alembic upgrade head

# Inspect current revision
.venv/bin/alembic current

# Inspect migration history
.venv/bin/alembic history
```

For a complete Compose deployment, the `migrate` service applies changes before
the API and worker start. Local development requires the explicit migration step.

The baseline and isolation migrations intentionally refuse unsafe downgrades.
Back up existing data before schema upgrades. PostgreSQL data is stored in the
Compose-managed `sentinel_pgdata` named volume.

## Tests and verification

### Backend unit tests

```sh
.venv/bin/python -m unittest discover -s tests
```

Database integration tests are skipped unless explicitly enabled. Authentication
unit tests use an isolated SQLite database.

### PostgreSQL integration tests

Start PostgreSQL and apply migrations, then run:

```sh
SENTINEL_RUN_DB_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

Integration fixtures roll back. Embedding and relevant external AI/email calls
are mocked in the integration tests. The suite covers authentication, session
revocation/expiry, CSRF, throttling, recommendations, actions, alerts, digests,
workflow routing, and account isolation.

Isolation regressions include two accounts and historical unassigned records;
they exercise guessed-ID reads/mutations, independent source URLs, private profile
creation and updates, memory search, separate digest periods and pending actions,
worker profile/memory context, and owner-specific email recipients.

### Frontend checks

```sh
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The build uses Webpack. The repository does not currently include an automated
frontend browser-test script in `package.json`; TypeScript and production builds
are its reproducible frontend checks.

## Troubleshooting

### Database connection refused on port 5430

PostgreSQL may have been stopped. Start it before migrations or backend use:

```sh
docker compose up -d --wait postgres
.venv/bin/alembic upgrade head
```

Check that the local `DATABASE_URL` uses host port **5430**, not container port
5432. An API `/health` response does not prove the database is reachable.

### Address already in use

An existing process is listening on the API or frontend port. On macOS, inspect
it before stopping anything:

```sh
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

If Sentinel is already running in another terminal, use that instance or stop it
with Ctrl+C. Avoid starting a duplicate local service or running it alongside the
Compose version on the same port.

### Backend unavailable in the frontend

Check that the API is running on the address in `BACKEND_URL`, that PostgreSQL is
available, and that migrations have been applied. Restart the frontend after
changing `frontend/.env.local`. For Compose, inspect `api` and `frontend` logs.

### Checks stay pending or intelligence is empty

Ensure the worker is running. A successful first check only establishes the
baseline; later changes produce findings. Queue retries can delay completion.
Inspect job status through `/watches/check-jobs/{job_id}` and the worker logs.

Complete the profile for personalized relevance. A new account has no shared
historical data; unassigned records from the old shared workspace are hidden.

### Gemini or Chromium failures

Verify `GEMINI_API_KEY` and model access, then inspect worker errors for request
failures or quota limits. If Chromium is missing, install it:

```sh
.venv/bin/python -m playwright install chromium
```

Some sites block automated requests or require login; browser fallback does not
provide authenticated browsing sessions for monitored sources.

### Login or mutations return 403/429

Use the frontend's configured URL. For another hostname, scheme, or port, update
`FRONTEND_ORIGINS` and restart the API and worker. Mutation calls need the CSRF
header; browser/proxy calls also need a valid Origin.

A 429 during authentication means the shared peer attempt budget was exhausted;
wait for the 15-minute window to reset. In local HTTP development,
`AUTH_COOKIE_SECURE` should remain false.

### Development WebSocket/HMR messages or stale favicon errors

`[HMR] connected` is a development hot-reload message. A connection can close while
the server restarts or the page reloads; check whether it reconnects. The favicon
is provided by `frontend/app/favicon.ico`.

Clear the browser console and hard-refresh with **Cmd+Shift+R** on macOS or
**Ctrl+Shift+R** on Windows/Linux. If reconnect failures continue, check the running
frontend process and any proxy handling WebSocket upgrades.

### Emails stay pending or sending

Pending delivery needs `SMTP_HOST` and `SMTP_FROM`, plus valid SMTP credentials
when required. Recipients are account emails, not `NOTIFICATION_EMAIL_TO`.
A `sending` row needs manual delivery review before resetting it for retry.

## Deployment notes

Use the Compose deployment for the included standalone frontend packaging. Its
frontend image builds Next.js, copies `.next/standalone` and static assets, and
runs the generated `server.js` as the non-root `node` user.

For HTTPS hosting, configure:

```dotenv
FRONTEND_URL=https://sentinel.example.com
FRONTEND_ORIGINS=https://sentinel.example.com
AUTH_COOKIE_SECURE=true
```

Keep `BACKEND_URL` pointed at the API address reachable by the frontend server.
A reverse proxy must preserve the public Host/Origin relationship for browser
mutation checks and forward WebSocket upgrades when using a development server.

The supplied Compose credentials and published database port are intended for
local setup. Set deployment-specific database credentials and exposure rules,
keep secret environment files out of version control, and arrange database
backups. Run migrations before starting updated API/worker code. The worker is a
separate required service in deployment as well as development.

## Project structure

```text
sentinel/
├── README.md
├── .env.example                 # Safe local configuration template
├── requirements.txt             # Python dependency constraints
├── Dockerfile                   # API/worker image with Chromium
├── docker-compose.yml           # Database, migrations, API, worker, frontend
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/                # Schema migrations
├── app/
│   ├── main.py                  # FastAPI app, routes, request logging
│   ├── worker.py                # Standalone scheduler/worker entry point
│   ├── config.py                # Environment-backed settings
│   ├── database.py              # SQLAlchemy engine and sessions
│   ├── api/                     # Auth and account-scoped endpoints
│   ├── models/                  # Persisted ORM entities
│   ├── schemas/                 # Request/response validation
│   ├── services/                # Monitoring, workflow, memory, delivery
│   └── static/                  # Historical static UI assets
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── Dockerfile               # Standalone Next.js runtime
│   ├── .env.example             # Server-only backend URL template
│   ├── app/
│   │   ├── api/[...path]/route.ts # FastAPI proxy
│   │   ├── login/               # Login page
│   │   ├── signup/              # Signup page
│   │   ├── favicon.ico
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx             # Dashboard entry
│   ├── components/              # Authentication form and dashboard
│   └── lib/api.ts               # Typed client requests and API errors
└── tests/                       # Unit and opt-in database integration tests
```

The old static assets are retained in the repository; FastAPI's `/control-center`
redirects to the Next.js frontend instead of serving that historical demo.

## Current limitations

- Authentication includes signup/login/logout, but not password reset, email
  verification, MFA, or account deletion.
- Source controls support creation, listing, pause/resume, and checks. Source
  deletion and editing other source fields are not exposed by the current API.
- Profile replacement and semantic memory operations depend on Gemini embeddings;
  there is no offline embedding fallback.
- SMTP credentials, reporting timezone, and request budgets are deployment-wide,
  although intelligence data and delivery recipients are account-specific.
- Action updates track progress; Sentinel does not submit job applications or
  execute the suggested actions for you.
- The application has no connected conversational chat endpoint.
- Website monitoring is best effort; source access, page structure, model access,
  and third-party limits affect results.

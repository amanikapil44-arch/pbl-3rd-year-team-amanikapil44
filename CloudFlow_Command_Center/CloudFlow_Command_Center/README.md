# CloudFlow – Multi-user Job Management

CloudFlow is a Flask + SQLite job tracker with isolated user accounts, a simulated worker scheduler, job history, logs and utilization statistics.

## Included improvements

- Registration, login and logout-ready session API; password hashes, HttpOnly/SameSite cookies and CSRF token validation on state-changing API requests.
- Every job, summary, statistic, detail view, retry and notification is scoped to the signed-in user.
- Retry/re-run endpoint and UI button for finished jobs.
- In-app notifications when simulated jobs finish or fail.
- Paginated job listing (`limit`, `offset`), sorting (`sort`, `order`) and literal-safe search.
- Rejects jobs that cannot fit on any worker; database indexes for status, user jobs and logs.
- Utilization retention increased to 5,000 samples.
- Pytest API tests, Docker/Gunicorn setup, dedicated scheduler process and GitHub Actions test workflow.

## Run locally

```bash
cd cloudflow
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 and create an account. The app defaults to listening on localhost only. Set `HOST=0.0.0.0` only when you intentionally want LAN access and have configured a strong secret and network controls.

## Docker deployment

```bash
cp .env.example .env
# Replace CLOUDFLOW_SECRET_KEY with a long random secret
# For example: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

The web service uses one Gunicorn worker and a separate scheduler container. Both share the SQLite volume. For multiple web replicas or substantial multi-user workloads, migrate to PostgreSQL and use a durable queue (Celery/RQ); SQLite is not a distributed job queue.

## Environment

- `CLOUDFLOW_SECRET_KEY`: required strong secret for deployment.
- `CLOUDFLOW_DB`: SQLite database path (default `cloudflow.db` beside `app.py`).
- `CLOUDFLOW_TICK`: scheduler interval in seconds (default `2`).
- `HOST` / `PORT`: local development bind (defaults `127.0.0.1:5000`).
- `COOKIE_SECURE=1`: mark session cookies Secure when served over HTTPS.

## API highlights

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Sign in |
| GET | `/api/auth/me` | Current session + CSRF token |
| POST | `/api/auth/logout` | Sign out |
| GET | `/api/jobs?limit=50&offset=0&sort=created_at&order=desc` | Paginated jobs |
| POST | `/api/jobs` | Submit job |
| GET | `/api/jobs/<id>` | Job details and logs |
| POST | `/api/jobs/<id>/cancel` | Cancel active job |
| POST | `/api/jobs/<id>/retry` | Clone and re-run a finished job |
| GET | `/api/notifications` | In-app notifications |
| POST | `/api/notifications/read` | Mark notifications read |
| GET | `/api/workers` | Worker utilization |
| GET | `/api/stats` | User job statistics |

For POST requests other than login/register, send the `csrf_token` returned by `/api/auth/me` or login/register in the `X-CSRF-Token` header.

## Important execution/security note

This version intentionally keeps execution simulated. The submitted `command` is stored and displayed but is **never executed**. Running arbitrary user commands directly in a Flask process would be unsafe. A production real-execution backend should dispatch to isolated, short-lived containers with strict CPU/RAM/GPU limits, non-root users, filesystem/network restrictions, timeouts and output limits. Email, webhooks, browser push, uploads/artifacts, cron scheduling, worker administration and a real distributed queue are not enabled yet.

## Tests

```bash
pytest -q
```

## CloudFlow Intelligence Lab (balanced upgrade)

The dashboard now includes an **AI Lab** navigation item with:

- **Job Optimizer:** transparent rule-based CPU/RAM/GPU recommendations by workload type. It is a heuristic, not a trained optimizer.
- **Failure Risk:** explainable risk score using worker capacity/utilization and the signed-in user's job history. It is a heuristic, not a predictive ML model.
- **Smart Recovery:** opt-in automatic retry for simulated failures, with a configurable maximum of 0–3 retries. Manual re-run remains available.
- **What-if Simulator:** estimates how many pending jobs could fit if hypothetical workers were added. It does not provision infrastructure.
- **Workflow Builder:** creates sequential job pipelines; each step waits for its predecessor to complete. If a dependency fails or is cancelled, downstream steps are marked failed.
- **CloudFlow Assistant:** local rule-based natural-language shortcuts for failed jobs, pending jobs, workers and cancellation guidance. It does not use an external LLM and never performs destructive actions.
- **Carbon Estimator:** illustrative energy/carbon estimate based on disclosed power assumptions and a user-entered grid intensity. It is not live grid data or a metered measurement.

These capabilities preserve the project's simulated execution model. Job `command` text is still stored for display and is never executed. For real production execution, use isolated containers and a durable task queue.

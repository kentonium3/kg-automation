---
title: TeamSpace (spec-kitty-saas) Local QA Setup
doc_type: runbook
audience: agents_and_humans
status: draft
created: 2026-07-15
last_validated: 2026-07-15
last_updated: '2026-07-15'
version: v1.0
owners: [kgale]
---

# TeamSpace (spec-kitty-saas) Local QA Setup

How the local **TeamSpace** QA environment is stood up, validated, and restarted.
TeamSpace (working name) = `Priivacy-ai/spec-kitty-saas` — the hosted
collaboration/presentation layer over the spec-kitty CLI. Kent owns **full QA**
for this product.

> **Mode note:** spec-kitty-saas is a *product we QA*, not a workflow manager.
> The kg-automation / Felix conventions and spec-kitty workflow rules do **not**
> apply to its source; any code change is branch + PR. This runbook is about
> *running and exercising* it locally.

Initial bring-up: **2026-07-15** (Robert Douglass' quickstart instructions,
filled in from the repo's own docs). Propagation validated the same day.

---

## 1. Repos (siblings under `~/repos/`)

| Repo | Role | Install note |
|---|---|---|
| `spec-kitty-saas` | The Django app (TeamSpace) | Docker stack |
| `spec-kitty-telescope` | "Telescope" event-observability tool | `uv tool install .` → `telescope` on PATH |
| `spec-kitty-design` | Design tokens (UI work only) | not needed for QA runtime |

Cloned via `gh repo clone <repo>` — **SSH keys are not set up**, so `git@github`
clone fails; `gh` uses the HTTPS keyring token (`unset GITHUB_TOKEN` first if org
scope errors appear).

Stack: Django 6 / Daphne ASGI, Postgres, Redis, Celery, HTMX + Alpine +
Tailwind/DaisyUI + Vite. Postgres is **5432** in Docker mode (ONBOARDING's 5433
is for the host-run `make local-db-bootstrap` path).

---

## 2. Bring up the SaaS stack (from `~/repos/spec-kitty-saas`)

```bash
make setup-env                 # creates .env from .env.example (idempotent)
# One-time: enable the Telescope SaaS-logs plane in .env (see step 4)
make docker-app-up-live        # db, redis, web, worker, beat, vite  (first run builds the image, ~several min)
```

Surfaces once up:

| Surface | URL |
|---|---|
| TeamSpace SaaS | http://localhost:8000 |
| Vite hot-reload | http://localhost:5173 |
| Postgres / Redis | localhost:5432 / :6379 |

Health: `curl http://localhost:8000/health/ready/` → `200`.
Stop: `make docker-app-down-live`.

**⚠️ `.env` reload footgun:** `env_file` is read at container-**create** time.
If you edit `.env` after `up`, a plain restart keeps the stale values — you must
force-recreate:

```bash
docker compose -f docker-compose.yml -f docker-compose.app.yml -f docker-compose.live.yml \
  up -d --force-recreate --no-deps web worker beat
```

---

## 3. Seed a login + demo data

```bash
make docker-auth-check-live    # bootstraps deterministic auth fixtures + smoke-tests login
make teamspace-seed-demo       # seeds team 'robert-team' with 4 demo projects
```

**Seeded QA user** (from `bootstrap_local_auth_fixtures`):

- Email: `docker-dev@example.com`
- Password: `devpass123`
- Team: `docker-dev` (id 1)  ·  Project: `docker-dev-project`

`robert-team` demo projects: field-prototype, atlas-core, signal-lab,
ops-watchtower.

---

## 4. Telescope (event observability, 3 planes)

**One-time SaaS `.env` additions** (then force-recreate per step 2):

```
TELESCOPE_ENABLED=true
TELESCOPE_ENVIRONMENT=local-docker
TELESCOPE_LOG_LEVEL=INFO
```

The middleware `apps.sync.telescope_hook.TelescopeLogMiddleware` is already
registered in `settings.py`; the env vars just switch it on. Verify:

```bash
docker compose -f docker-compose.yml -f docker-compose.app.yml -f docker-compose.live.yml \
  exec -T web python -c "from apps.sync import telescope_hook as h; print(h._ENABLED)"   # → True
```

**Run Telescope** (survives across terminals; restart after a reboot):

```bash
# Dashboard — watches the isolated QA CLI home (step 5)
telescope serve --host 127.0.0.1 --port 7878 --cli-home ~/.spec-kitty-qa   # → http://127.0.0.1:7878

# Attach — ingests SaaS TELESCOPE: log sentinels (NOTE: attach does NOT accept --cli-home)
telescope attach --env local-docker --source "stream:docker logs -f spec-kitty-saas-web-1"
```

---

## 5. Point the CLI at local + authenticate (isolated QA home)

We use a **dedicated `SPEC_KITTY_HOME`** so the ~7200-event backlog in the real
`~/.spec-kitty` (from prior Fly-era CLI work) can't drain into local TeamSpace.

Env file `~/.spec-kitty-qa-env.sh`:

```bash
export SPEC_KITTY_HOME="$HOME/.spec-kitty-qa"
export SPEC_KITTY_ENABLE_SAAS_SYNC=1          # Robert's "feature flag to 1"
export SPEC_KITTY_SAAS_URL=http://localhost:8000   # Robert's "point the env var at local Docker host"
```

```bash
source ~/.spec-kitty-qa-env.sh        # do this before ANY QA CLI work
spec-kitty sync server http://localhost:8000
spec-kitty auth login --force         # opens browser OAuth → log in docker-dev / devpass123 → Allow
spec-kitty auth whoami                # → docker-dev@example.com
```

- `auth login` reads **`SPEC_KITTY_SAAS_URL`** (not just the config file) — it
  errors if that env var is unset.
- CLI OAuth client id = `cli_native` (server validates it as a constant; no
  fixture needed).
- **Stale-cookie CSRF 403:** a leftover `localhost:8000` cookie from another
  Django app makes the browser login POST fail CSRF. Fix: DevTools → Application
  → Clear site data, hard-reload, retry. (Server-side CSRF is fine — proven with
  a fresh cookie jar.)

---

## 6. Validate propagation (the real method locally)

**Use the 3-plane manual comparison** — do NOT trust Telescope's
"delivered/missing" counter locally (see Findings #2).

```bash
source ~/.spec-kitty-qa-env.sh
mkdir -p ~/repos/teamspace-qa-scratch && cd ~/repos/teamspace-qa-scratch
git init -q && git commit -q --allow-empty -m init
spec-kitty init --ai claude --non-interactive     # emits BuildRegistered; a background sync auto-delivers
```

Check the three planes:

```bash
# Plane 1 — local emit
telescope status --minutes 60 --cli-home ~/.spec-kitty-qa

# Plane 2 — SaaS request logs (batch ingress)
docker logs spec-kitty-saas-web-1 2>&1 | grep 'TELESCOPE:' | tail

# Plane 3 — SaaS materialization (authoritative)
docker compose -f docker-compose.yml -f docker-compose.app.yml -f docker-compose.live.yml \
  exec -T web python manage.py shell -c "from apps.sync.models import Event; \
  print(Event.objects.count()); \
  [print(e.event_type, e.project_slug, e.team_id) for e in Event.objects.all()[:10]]"
```

**Validated 2026-07-15:** `spec-kitty init` on `teamspace-qa-scratch{,2}` →
`BuildRegistered` → `POST /api/v1/events/batch/` (200) → SaaS `Event` rows on
team `docker-dev` with correct `project_slug` → projected into
`is_teamspace_visible=True` Project rows (visible at
`/a/docker-dev/dashboards/`). Note: a manual `spec-kitty sync now` reports
`duplicate` because a background auto-sync already delivered on `init` — that's
success, not a failure. Build registration fires on `init`/mission actions, not
bare commits.

---

## 7. Findings from bring-up (candidates to report)

1. **Sync WebSocket 403 on local** — every CLI command logs
   `WARNING Sync WebSocket connection failed: HTTP 403`. Batch HTTP sync works,
   so it's non-blocking, but the live-push WS never connects locally. **Top
   report candidate.**
2. **Telescope "delivered/missing" misleading locally** — the shipped SaaS hook
   `apps/sync/telescope_hook.py` (85 lines) only logs *request-level* `TELESCOPE:`
   sentinels; it has no per-event receipt POST (`TELESCOPE_ENDPOINT`) path that
   the generic `django_hook/` version has. So Telescope can't match receipts to
   `event_id`s and shows everything "missing" even on success. Doc/UX gap vs.
   "Telescope compares the logs."
3. `team_slug: null` in sentinels for `/api/v1/events/batch/` (regex only matches
   `/a/<slug>/`). Cosmetic observability gap.
4. CSRF verbose page from stale browser cookie (environmental, not a bug; noted
   for first-run-dev confusion).
5. `.env` reload footgun (§2) — Makefile/docs could call it out.

---

## 8. Deferred / blocked

- **Nango connectors (Jira / Linear / Slack)** — need `NANGO_SECRET_KEY` +
  `NANGO_WEBHOOK_SIGNING_KEY` (blank in `.env.example`; no Nango account yet).
  Ask the team. The local auth-check simulates connector OAuth callbacks in-app,
  so the connectors *list* UI works without Nango, but real connections don't.

---

## 9. Restart cheatsheet (after reboot / lost session)

```bash
# 1. SaaS stack
cd ~/repos/spec-kitty-saas && make docker-app-up-live

# 2. Telescope (two processes)
telescope serve --host 127.0.0.1 --port 7878 --cli-home ~/.spec-kitty-qa &
telescope attach --env local-docker --source "stream:docker logs -f spec-kitty-saas-web-1" &

# 3. CLI env (per shell)
source ~/.spec-kitty-qa-env.sh
spec-kitty auth whoami   # re-run `spec-kitty auth login --force` if logged out
```

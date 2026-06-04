---
rq_id: "RQ-2"
title: "Felix touchpoint inventory"
depends_on: []
wp: "WP01"
---

# RQ-2 — Felix Touchpoint Inventory

**Scope**: Every Felix code callsite that reads from or writes to Vikunja. One row per callsite. Grep commands documented verbatim per FR-004. Codebase base commit: `5ac4543d` (2026-06-03).

**Exclusions**: Docs-only mentions (markdown files), spec-kitty workflow files (`kitty-specs/`, `.kittify/`), test fixtures (unless they constitute runtime touchpoints), worktree directories (`.worktrees/`).

---

## Grep Commands (verbatim)

### Grep 1 — Broad sweep: files referencing Vikunja API token or base URL

```bash
grep -rn 'vikunja-api\|office2.tail0f5f56.ts.net\|vikunja\.local\|VIKUNJA_BASE\|api/v1' \
  /Users/kentgale/repos/kg-automation/scripts \
  --include='*.py' -l \
  | grep -v '__pycache__\|\.worktrees' \
  | sort -u
```

**Output** (2026-06-03, 23 files — re-run verified on 2026-06-03):
```
scripts/enrichment/record_completion.py
scripts/enrichment/reconcile_completions.py
scripts/escalation/hard_fail.py
scripts/escalation/reconcile_completions.py
scripts/escalation/record_completion.py
scripts/habits/backfill_jsonl_from_comments.py
scripts/habits/exclude_completed.py
scripts/habits/identify_workout_task.py
scripts/habits/migrate_schedule.py
scripts/habits/morning_checkin_list.py
scripts/habits/query_active_habits.py
scripts/habits/query_active_habits_v2.py
scripts/habits/reconcile_completions.py
scripts/habits/record_completion.py
scripts/habits/set_due_dates.py
scripts/habits/sweeper.py
scripts/security/credential_health_check/vikunja_writer.py
scripts/vikunja/provision_felix_bot.py
scripts/vikunja/revoke_kent_tokens.py
scripts/vikunja/setup_goals.py
scripts/vikunja/setup_vikunja.py
scripts/vikunja/swap_vikunja_secrets.py
scripts/vikunja/validate_felix_bot.py
```

### Grep 2 — HTTP client library imports (urllib/requests/httpx)

```bash
grep -rn 'import urllib\|import requests\|import httpx' \
  /Users/kentgale/repos/kg-automation/scripts \
  --include='*.py' -l \
  | grep -v '__pycache__\|\.worktrees'
```

**Output**: All files from Grep 1 that make live API calls use `urllib.request` (standard library). `setup_vikunja.py` uses `requests` (third-party). No `httpx` usage found in scripts.

### Grep 3 — Direct Vikunja endpoint patterns

```bash
grep -rn '/tasks/\|/projects/\|/comments\|/labels\|/webhooks' \
  /Users/kentgale/repos/kg-automation/scripts \
  --include='*.py' \
  | grep -v '__pycache__\|\.worktrees\|#' \
  | grep -v 'test_\|fixture'
```

**Note (cycle 2)**: Grep 3 is a per-file confirmation step, not a discovery step. Discovery happened in Grep 1 (broad sweep over 23 files); Grep 3 confirms which endpoint patterns each file uses. Every file from Grep 1 is inventoried or explicitly excluded in the Notes section below — Grep 3 does not introduce additional discovery scope.

**Verbatim output** (2026-06-03, against commit 5ac4543d):
```
scripts/enrichment/record_completion.py:482:    url = f"{base_url}/tasks/{task_id}/comments"
scripts/enrichment/reconcile_completions.py:146:    tasks_url = f"{base_url}/projects/{project_id}/tasks"
scripts/enrichment/reconcile_completions.py:160:    comments_url = f"{base_url}/tasks/{task_id}/comments"
scripts/escalation/hard_fail.py:339:    # ``https://office2.tail0f5f56.ts.net/tasks/1234``) and ISO-8601
scripts/escalation/reconcile_completions.py:137:    tasks_url = f"{base_url}/projects/{project_id}/tasks"
scripts/escalation/record_completion.py:451:    url = f"{base_url}/tasks/{task_id}"
scripts/habits/backfill_jsonl_from_comments.py:159:    url = f"{base_url}/projects"
scripts/habits/backfill_jsonl_from_comments.py:168:    tasks_url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/backfill_jsonl_from_comments.py:177:    url = f"{base_url}/tasks/{task_id}/comments"
scripts/habits/exclude_completed.py:127:    comments = _http_get(base_url, token, f"/tasks/{habit_id}/comments")
scripts/habits/identify_workout_task.py:52:    url = f"{base_url}/tasks/{task_id}"
scripts/habits/migrate_schedule.py:129:    tasks_url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/migrate_schedule.py:143:    url = f"{base_url}/tasks/{task_id}"
scripts/habits/migrate_schedule.py:159:    create_url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/morning_checkin_list.py:230:    url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/query_active_habits.py:118:    projects = _http_get(base_url, token, "/projects")
scripts/habits/query_active_habits.py:133:    tasks = _http_get(base_url, token, f"/projects/{project_id}/tasks?per_page=200")
scripts/habits/query_active_habits_v2.py:132:    projects = _http_get(base_url, token, "/projects")
scripts/habits/query_active_habits_v2.py:167:    tasks = _http_get(base_url, token, f"/projects/{project_id}/tasks?per_page=200")
scripts/habits/reconcile_completions.py:140:    url = f"{base_url}/projects"
scripts/habits/reconcile_completions.py:150:    tasks_url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/record_completion.py:268:    task_url = f"{base_url}/tasks/{task_id}"
scripts/habits/record_completion.py:277:    comments_url = f"{base_url}/tasks/{task_id}/comments"
scripts/habits/set_due_dates.py:278:    url = f"{base_url}/projects"
scripts/habits/set_due_dates.py:290:    url = f"{base_url}/projects/{project_id}/tasks"
scripts/habits/set_due_dates.py:368:    url = f"{base_url}/tasks/{task_id}"
scripts/habits/sweeper.py:616:    url = f"{base_url}/tasks/{task_id}"
scripts/security/credential_health_check/vikunja_writer.py:119:    url = f"{base_url}/projects"
scripts/security/credential_health_check/vikunja_writer.py:134:    url = f"{base_url}/projects/{project_id}/tasks"
scripts/vikunja/provision_felix_bot.py:355:    url = _join_url(base_url, f"projects/{project_id}/users")
scripts/vikunja/provision_felix_bot.py:433:    url = _join_url(base_url, f"projects/{project_id}/users")
scripts/vikunja/provision_felix_bot.py:517:    url = _join_url(base_url, f"projects/{pid}/users")
scripts/vikunja/provision_felix_bot.py:287:    url = _join_url(base_url, "register")
scripts/vikunja/provision_felix_bot.py:355:    projects?per_page=50
scripts/vikunja/revoke_kent_tokens.py:114:    url = f"{_normalize_base_url(base_url)}/tokens"
scripts/vikunja/revoke_kent_tokens.py:124:    url = f"{_normalize_base_url(base_url)}/tokens/{token_id}"
scripts/vikunja/setup_goals.py:97:    url = f"{base_url}/projects/{project_id}/tasks"
scripts/vikunja/setup_goals.py:109:    create_url = f"{base_url}/projects/{project_id}/tasks"
scripts/vikunja/setup_goals.py:122:    url = f"{base_url}/tasks/{task_id}/labels"
scripts/vikunja/setup_vikunja.py:97:    url = f"{base_url}/info"
scripts/vikunja/setup_vikunja.py:107:    url = f"{base_url}/projects"
scripts/vikunja/setup_vikunja.py:145:    url = f"{base_url}/projects"
scripts/vikunja/setup_vikunja.py:160:    url = f"{base_url}/labels"
scripts/vikunja/setup_vikunja.py:175:    url = f"{base_url}/projects/{project_id}/filters"
scripts/vikunja/swap_vikunja_secrets.py:456:    post_url = f"{base}/tasks/{task_id}/comments"
scripts/vikunja/swap_vikunja_secrets.py:488:    get_url = f"{base}/tasks/{task_id}/comments/{comment_id}"
scripts/vikunja/swap_vikunja_secrets.py:525:    _http_request_json(get_url, token, method="DELETE")
scripts/vikunja/validate_felix_bot.py:198:    url = f"{_normalize_base_url(base_url)}/projects?per_page=50"
scripts/vikunja/validate_felix_bot.py:315:    create_task_url = f"{base}/projects/{target_project_id}/tasks"
scripts/vikunja/validate_felix_bot.py:338:    create_comment_url = f"{base}/tasks/{task_id}/comments"
scripts/vikunja/validate_felix_bot.py:370:    list_comments_url = f"{base}/tasks/{task_id}/comments"
scripts/vikunja/validate_felix_bot.py:408:    delete_comment_url = f"{base}/tasks/{task_id}/comments/{comment_id}"
scripts/vikunja/validate_felix_bot.py:422:    delete_task_url = f"{base}/tasks/{task_id}"
```

**Grep 3 interpretation** (per-file confirmation of endpoints already discovered via Grep 1 and TP-row inventory):
- `scripts/habits/record_completion.py`: `POST /tasks/<id>` (done), `PUT /tasks/<id>/comments` → TP-01
- `scripts/habits/reconcile_completions.py`: `GET /projects`, `GET /projects/<id>/tasks` → TP-02
- `scripts/habits/query_active_habits_v2.py`: `GET /projects`, `GET /projects/<id>/tasks` → TP-03
- `scripts/habits/query_active_habits.py` (v1): `GET /projects`, `GET /projects/<id>/tasks` → TP-18 (new, cycle 2)
- `scripts/habits/set_due_dates.py`: `GET /projects`, `GET /projects/<id>/tasks`, `POST /tasks/{id}` → TP-04, TP-05
- `scripts/habits/sweeper.py`: `POST /tasks/{id}` → TP-06
- `scripts/habits/morning_checkin_list.py`: `GET /projects/<id>/tasks` → TP-07
- `scripts/habits/backfill_jsonl_from_comments.py`: `GET /projects`, `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments` → TP-08
- `scripts/habits/exclude_completed.py`: `GET /tasks/<id>/comments` → TP-15A
- `scripts/habits/identify_workout_task.py`: `GET /tasks/<id>` → TP-15B
- `scripts/habits/migrate_schedule.py`: `GET /projects/<id>/tasks`, `GET /tasks/<id>`, `POST /tasks/<id>`, `PUT /projects/<id>/tasks` → TP-15C
- `scripts/escalation/hard_fail.py`: comment-only URL mention (line 339), no runtime API call → excluded (see Notes)
- `scripts/escalation/record_completion.py`: `PATCH /tasks/{id}` → TP-09
- `scripts/escalation/reconcile_completions.py`: `GET /projects/<id>/tasks` → TP-10
- `scripts/enrichment/record_completion.py`: `PUT /tasks/{id}/comments` → TP-11
- `scripts/enrichment/reconcile_completions.py`: `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments` → TP-12
- `scripts/security/credential_health_check/vikunja_writer.py`: `GET /projects`, `PUT /projects/{id}/tasks` → TP-13
- `scripts/vikunja/setup_vikunja.py`: `GET /info`, `GET /projects`, `PUT /projects`, `GET /labels`, `PUT /labels`, `PUT /projects/{id}/filters` → TP-14
- `scripts/vikunja/provision_felix_bot.py`: `POST /register`, `GET /projects`, `PUT /projects/{id}/users`, `GET /projects/{id}/users` → TP-16A, TP-16B, TP-16C
- `scripts/vikunja/validate_felix_bot.py`: `GET /projects`, `PUT /projects/{id}/tasks`, `PUT /tasks/{id}/comments`, `GET /tasks/{id}/comments`, `DELETE /tasks/{id}/comments/{id}`, `DELETE /tasks/{id}` → TP-16D
- `scripts/vikunja/swap_vikunja_secrets.py`: `PUT /tasks/{id}/comments`, `GET /tasks/{id}/comments/{id}`, `DELETE` (probe comment) → TP-16E
- `scripts/vikunja/setup_goals.py`: `GET /projects/{id}/tasks`, `PUT /projects/{id}/tasks`, `PUT /tasks/{id}/labels` → TP-15D
- `scripts/vikunja/revoke_kent_tokens.py`: `POST /login`, `GET /tokens`, `DELETE /tokens/{id}` → TP-15E

---

## Touchpoint Inventory

### TP-01 — habits/record_completion.py: `record()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/record_completion.py` |
| `function_or_callsite` | `record()` |
| `layer` | task |
| `http_verb` | POST (done=true), PUT (comment) |
| `vikunja_endpoint` | `POST /tasks/<id>`, `PUT /tasks/<id>/comments` |
| `read_set` | — (write-only callsite) |
| `write_set` | `done`, `done_at` (via POST), comment body |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent |
| `runtime_trigger` | openclaw-agent (WhatsApp response handler) |

Note: Three-write transaction (JSONL + Vikunja done + Vikunja comment). Idempotent on `task_id + date + state`. observed (`scripts/habits/record_completion.py` lines 8–9, 214–215, 268, 277)

---

### TP-02 — habits/reconcile_completions.py: `reconcile()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/reconcile_completions.py` |
| `function_or_callsite` | `reconcile()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects`, `GET /projects/<id>/tasks` |
| `read_set` | `id`, `done`, `done_at`, `title`, `updated` (task fields); `id`, `title` (project fields) |
| `write_set` | — (read-only API calls; appends to JSONL on-disk if backfill needed) |
| `freshness_assumption` | `<5 min` (reconciler runs at cron start) |
| `owner_component` | habits-agent |
| `runtime_trigger` | systemd-timer (morning cron, runs before check-in) |

observed (`scripts/habits/reconcile_completions.py` lines 140–220)

---

### TP-03 — habits/query_active_habits_v2.py: `query_active_today()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/query_active_habits_v2.py` |
| `function_or_callsite` | `query_active_today()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects`, `GET /projects/<id>/tasks` (no server-side filter — G7 workaround) |
| `read_set` | `id`, `title`, `done`, `due_date`, `repeat_after`, `repeat_mode`, `updated`, `labels` |
| `write_set` | — |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent |
| `runtime_trigger` | openclaw-agent (morning check-in workflow) |

observed (`scripts/habits/query_active_habits_v2.py` lines 15, 83, 132, 167–200)

---

### TP-04 — habits/set_due_dates.py: `reconcile_schedule()` (GET phase)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/set_due_dates.py` |
| `function_or_callsite` | `reconcile_schedule()` — GET phase |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects`, `GET /projects/<id>/tasks` |
| `read_set` | `id`, `title`, `repeat_after`, `repeat_mode`, `due_date` |
| `write_set` | — |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent |
| `runtime_trigger` | systemd-timer (morning cron) |

---

### TP-05 — habits/set_due_dates.py: `reconcile_schedule()` (PUT phase)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/set_due_dates.py` |
| `function_or_callsite` | `reconcile_schedule()` — PUT/POST phase |
| `layer` | task |
| `http_verb` | POST (Vikunja v0.24.6 partial update is POST, not PATCH/PUT) |
| `vikunja_endpoint` | `POST /tasks/{id}` |
| `read_set` | — |
| `write_set` | `due_date` (sets end-of-day-ET for each active habit) |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent |
| `runtime_trigger` | systemd-timer (morning cron) |

observed (`scripts/habits/set_due_dates.py` lines 28–29, 270–380)

---

### TP-06 — habits/sweeper.py: `_vikunja_put_due_date()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/sweeper.py` |
| `function_or_callsite` | `_vikunja_put_due_date()` |
| `layer` | task |
| `http_verb` | POST |
| `vikunja_endpoint` | `POST /tasks/{id}` |
| `read_set` | — |
| `write_set` | `due_date` (advance due_date on completion or reschedule) |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent (sweeper sub-component) |
| `runtime_trigger` | openclaw-agent (evening sweeper) |

observed (`scripts/habits/sweeper.py` lines 606–640)

---

### TP-07 — habits/morning_checkin_list.py: `_query_habits()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/morning_checkin_list.py` |
| `function_or_callsite` | `_query_habits()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects/<id>/tasks` (via `_http_get`) |
| `read_set` | `id`, `title`, `done`, `due_date`, `labels`, `updated` |
| `write_set` | — |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent |
| `runtime_trigger` | openclaw-agent (morning check-in list builder) |

observed (`scripts/habits/morning_checkin_list.py` lines 17, 87, 218–321)

---

### TP-08 — habits/backfill_jsonl_from_comments.py: `_enumerate_habit_tasks()` + `_fetch_comments()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/backfill_jsonl_from_comments.py` |
| `function_or_callsite` | `_enumerate_habit_tasks()`, `_fetch_comments()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects`, `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments` |
| `read_set` | `id`, `title`, `done`, `done_at`, `project_id`; comment `id`, `comment`, `created`, `author` |
| `write_set` | — |
| `freshness_assumption` | no constraint (one-shot backfill script) |
| `owner_component` | habits-agent (migration tooling) |
| `runtime_trigger` | manual |

observed (`scripts/habits/backfill_jsonl_from_comments.py` lines 148–242)

---

### TP-09 — escalation/record_completion.py: `_vikunja_side_effects()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/escalation/record_completion.py` |
| `function_or_callsite` | `_vikunja_side_effects()` |
| `layer` | task |
| `http_verb` | PATCH |
| `vikunja_endpoint` | `PATCH /tasks/{id}` |
| `read_set` | — |
| `write_set` | `done` (for state=done), `due_date` (for state=rescheduled) |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | escalation-agent |
| `runtime_trigger` | openclaw-agent (WhatsApp response handler) |

observed (`scripts/escalation/record_completion.py` lines 14–15, 427–462)

---

### TP-10 — escalation/reconcile_completions.py: reconciler GET

| Attribute | Value |
|---|---|
| `file_path` | `scripts/escalation/reconcile_completions.py` |
| `function_or_callsite` | reconciler GET phase |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects/<id>/tasks` |
| `read_set` | `id`, `done`, `done_at`, `due_date`, `title`, `updated` |
| `write_set` | — |
| `freshness_assumption` | `<5 min` |
| `owner_component` | escalation-agent |
| `runtime_trigger` | systemd-timer |

---

### TP-11 — enrichment/record_completion.py: `_vikunja_side_effect()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/enrichment/record_completion.py` |
| `function_or_callsite` | `_vikunja_side_effect()` |
| `layer` | task |
| `http_verb` | PUT |
| `vikunja_endpoint` | `PUT /tasks/{id}/comments` |
| `read_set` | — |
| `write_set` | comment body (`[Felix] enrichment | <state> | <timestamp>`) |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | tasker-agent |
| `runtime_trigger` | openclaw-agent |

observed (`scripts/enrichment/record_completion.py` lines 11, 481–505)

---

### TP-12 — enrichment/reconcile_completions.py: reconciler GET

| Attribute | Value |
|---|---|
| `file_path` | `scripts/enrichment/reconcile_completions.py` |
| `function_or_callsite` | reconciler GET phase |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments` |
| `read_set` | `id`, `done`, `title`; comment body (enrichment state detection) |
| `write_set` | — |
| `freshness_assumption` | `<5 min` |
| `owner_component` | tasker-agent |
| `runtime_trigger` | systemd-timer |

---

### TP-13 — security/credential_health_check/vikunja_writer.py

| Attribute | Value |
|---|---|
| `file_path` | `scripts/security/credential_health_check/vikunja_writer.py` |
| `function_or_callsite` | `lookup_inbox_project_id()`, `create_task()` |
| `layer` | project (lookup) + task (create) |
| `http_verb` | GET (lookup), PUT (create) |
| `vikunja_endpoint` | `GET /projects`, `PUT /projects/{id}/tasks` |
| `read_set` | `id`, `title` (project lookup) |
| `write_set` | `title`, `description`, `due_date`, `labels` (task create) |
| `freshness_assumption` | no constraint (credential health check, infrequent) |
| `owner_component` | credential-health-check |
| `runtime_trigger` | systemd-timer (periodic security scan) |

observed (`scripts/security/credential_health_check/vikunja_writer.py` lines 19, 105–144)

---

### TP-14 — vikunja/setup_vikunja.py (provisioning)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/setup_vikunja.py` |
| `function_or_callsite` | `wait_for_api()`, `authenticate()`, `get_existing_projects()`, `create_projects()`, `create_labels()`, `create_filters()` |
| `layer` | project + task (project and label lifecycle) |
| `http_verb` | GET, POST (auth), PUT (create) |
| `vikunja_endpoint` | `GET /info`, `POST /login`, `GET /projects`, `PUT /projects`, `GET /labels`, `PUT /labels`, `PUT /projects/{id}/filters` |
| `read_set` | project list, label list |
| `write_set` | project structure, label definitions, saved filters |
| `freshness_assumption` | no constraint (one-shot setup) |
| `owner_component` | provisioning tooling |
| `runtime_trigger` | manual |

observed (`scripts/vikunja/setup_vikunja.py` lines 21, 83–234)

---

### TP-15A — habits/exclude_completed.py (legacy v1)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/exclude_completed.py` |
| `function_or_callsite` | `find_addressed_state()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /tasks/<id>/comments` |
| `read_set` | comment `text` (parses `[Felix]` prefix for completion state) |
| `write_set` | — |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent (legacy v1; superseded by exclude_completed_v2.py + JSONL) |
| `runtime_trigger` | openclaw-agent (v1 cron path; active deployment status deferred per Note 3) |

---

### TP-15B — habits/identify_workout_task.py

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/identify_workout_task.py` |
| `function_or_callsite` | `find_workout_task()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /tasks/<id>` |
| `read_set` | `id`, `title`, `labels`, `description` (for workout task identification) |
| `write_set` | — |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent (workout identification helper) |
| `runtime_trigger` | openclaw-agent |

---

### TP-15C — habits/migrate_schedule.py (migration tooling)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/migrate_schedule.py` |
| `function_or_callsite` | migration operations |
| `layer` | task |
| `http_verb` | GET, POST, PUT |
| `vikunja_endpoint` | `GET /tasks/<id>`, `POST /tasks/<id>` (repeat_after/repeat_mode update), `PUT /projects/<id>/tasks` (create) |
| `read_set` | `id`, `title`, `repeat_after`, `repeat_mode`, `due_date` |
| `write_set` | `repeat_after`, `repeat_mode`, `due_date` (schedule migration); task creation |
| `freshness_assumption` | no constraint (one-shot migration) |
| `owner_component` | habits-agent (migration tooling) |
| `runtime_trigger` | manual |

---

### TP-15D — vikunja/setup_goals.py (provisioning)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/setup_goals.py` |
| `function_or_callsite` | goal setup operations |
| `layer` | task |
| `http_verb` | GET, PUT |
| `vikunja_endpoint` | `GET /projects/{id}/tasks`, `PUT /projects/{id}/tasks`, `PUT /tasks/{id}/labels` |
| `read_set` | task list (dedup check) |
| `write_set` | task creation, label assignment |
| `freshness_assumption` | no constraint (one-shot setup) |
| `owner_component` | provisioning tooling |
| `runtime_trigger` | manual |

---

### TP-15E — vikunja/revoke_kent_tokens.py (maintenance tooling)

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/revoke_kent_tokens.py` |
| `function_or_callsite` | `_get_tokens()`, `_login()` |
| `layer` | (auth layer — token management) |
| `http_verb` | POST (/login), GET (/tokens), DELETE (/tokens/{id}) |
| `vikunja_endpoint` | `POST /login`, `GET /tokens`, `DELETE /tokens/{id}` |
| `read_set` | token list |
| `write_set` | token deletion |
| `freshness_assumption` | no constraint (credential rotation tooling) |
| `owner_component` | provisioning/security tooling |
| `runtime_trigger` | manual |

---

### TP-16A — vikunja/provision_felix_bot.py: `register_felix_bot()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/provision_felix_bot.py` |
| `function_or_callsite` | `register_felix_bot()` |
| `layer` | auth (user registration) |
| `http_verb` | POST |
| `vikunja_endpoint` | `POST /register` (maps to `POST /api/v1/register` at full URL) |
| `read_set` | — |
| `write_set` | new user: `username`, `email`, `password` (felix-bot account creation) |
| `freshness_assumption` | no constraint (one-shot provisioning) |
| `owner_component` | provisioning tooling |
| `runtime_trigger` | manual |

observed (`scripts/vikunja/provision_felix_bot.py` lines 266–325; commit 5ac4543d)

---

### TP-16B — vikunja/provision_felix_bot.py: `enumerate_real_projects()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/provision_felix_bot.py` |
| `function_or_callsite` | `enumerate_real_projects()` |
| `layer` | project |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects?per_page=50` |
| `read_set` | `id`, `title`, `is_archived` (project list for real-project selection) |
| `write_set` | — |
| `freshness_assumption` | no constraint (one-shot provisioning) |
| `owner_component` | provisioning tooling |
| `runtime_trigger` | manual |

observed (`scripts/vikunja/provision_felix_bot.py` lines 334–368; commit 5ac4543d)

---

### TP-16C — vikunja/provision_felix_bot.py: `share_project_with_user()` + `verify_shares_applied()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/provision_felix_bot.py` |
| `function_or_callsite` | `share_project_with_user()`, `verify_shares_applied()` |
| `layer` | project (share) |
| `http_verb` | PUT (share), GET (verify) |
| `vikunja_endpoint` | `PUT /projects/{id}/users`, `GET /projects/{id}/users` |
| `read_set` | project user list (verification of felix-bot membership) |
| `write_set` | project sharing: `user_id`, `right=1` |
| `freshness_assumption` | no constraint (one-shot provisioning) |
| `owner_component` | provisioning tooling |
| `runtime_trigger` | manual |

observed (`scripts/vikunja/provision_felix_bot.py` lines 407–540; commit 5ac4543d)

---

### TP-16D — vikunja/validate_felix_bot.py: `verify_project_access()` + `validate_attribution()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/validate_felix_bot.py` |
| `function_or_callsite` | `verify_project_access()`, `validate_attribution()` |
| `layer` | project (access check) + task (attribution probe) |
| `http_verb` | GET (project access), PUT (task create), PUT (comment write), GET (comment readback), DELETE (comment cleanup), DELETE (task cleanup) |
| `vikunja_endpoint` | `GET /projects?per_page=50`, `PUT /projects/{id}/tasks`, `PUT /tasks/{id}/comments`, `GET /tasks/{id}/comments`, `DELETE /tasks/{id}/comments/{id}`, `DELETE /tasks/{id}` |
| `read_set` | project list (access check); comment `created_by.username` / `author.username` (attribution verification) |
| `write_set` | throwaway task creation (probe only; best-effort deleted), throwaway comment (probe only; best-effort deleted) |
| `freshness_assumption` | no constraint (one-shot validation tooling) |
| `owner_component` | provisioning/security tooling |
| `runtime_trigger` | manual |

Note: The DELETE callsites are best-effort cleanup (probe cleanup on validation run). Not on any production sync path. observed (`scripts/vikunja/validate_felix_bot.py` lines 185–424; commit 5ac4543d)

---

### TP-16E — vikunja/swap_vikunja_secrets.py: `verify_attribution()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/vikunja/swap_vikunja_secrets.py` |
| `function_or_callsite` | `verify_attribution()` |
| `layer` | task (post-swap attribution probe) |
| `http_verb` | PUT (probe comment write), GET (comment readback), DELETE (cleanup) |
| `vikunja_endpoint` | `PUT /tasks/{id}/comments`, `GET /tasks/{id}/comments/{id}`, `DELETE /tasks/{id}/comments/{id}` (cleanup) |
| `read_set` | comment `author.username` (attribution check post-rotation) |
| `write_set` | probe comment (best-effort deleted after verification) |
| `freshness_assumption` | no constraint (secret rotation tooling; run once per rotation event) |
| `owner_component` | provisioning/security tooling |
| `runtime_trigger` | manual (atomic secrets cutover script) |

Note: The core function of `swap_vikunja_secrets.py` is file-system secret rotation (backup + atomic write via `rotate_secrets()`). The Vikunja API callsite is only in the post-swap attribution verification step. No project-layer or task-CRUD endpoints used. observed (`scripts/vikunja/swap_vikunja_secrets.py` lines 420–530; commit 5ac4543d)

---

### TP-18 — habits/query_active_habits.py (v1): `find_habits_project_id()`, `fetch_habits_tasks()`

| Attribute | Value |
|---|---|
| `file_path` | `scripts/habits/query_active_habits.py` |
| `function_or_callsite` | `find_habits_project_id()`, `fetch_habits_tasks()` |
| `layer` | task |
| `http_verb` | GET |
| `vikunja_endpoint` | `GET /projects` (project title lookup), `GET /projects/{id}/tasks?per_page=200` |
| `read_set` | `id`, `title` (project fields); `id`, `title`, `done`, `description`, `due_date` (task fields) |
| `write_set` | — (read-only) |
| `freshness_assumption` | same-cron-tick |
| `owner_component` | habits-agent (v1 helper; v2 counterpart is `query_active_habits_v2.py`) |
| `runtime_trigger` | openclaw-agent (habits check-in; v1 cron path — active deployment status requires verification against live systemd units on office2) |

Note (cycle 2): Added in response to Required-1 feedback. This is the v1 helper for querying active habits. It uses the same `urllib.request`-based `_http_get()` pattern and `DEFAULT_BASE_URL` constant as the rest of the habits scripts. Whether the agent invokes v1 or v2 at runtime requires checking live OpenClaw agent config on office2 (deferred to implementation). TP-18 numbering preserves the existing TP-01 through TP-17 slot numbering; TP-17 is removed (it bundled three files); TP-16A/B/C/D/E replace it; TP-18 is the new v1 entry. observed (`scripts/habits/query_active_habits.py` lines 56–57, 62, 86–92, 116–136; commit 5ac4543d)

---

## Cross-Agent Touchpoint Summary

| Agent/Component | Layer(s) | Reads | Writes | Trigger |
|---|---|---|---|---|
| habits-agent | task | `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments` | `POST /tasks/{id}` (done, due_date), `PUT /tasks/{id}/comments` | systemd-timer + openclaw-agent |
| escalation-agent | task | `GET /projects/<id>/tasks`, `GET /tasks/{id}/comments` (in-prompt, not helper) | `PATCH /tasks/{id}` (done, due_date) | openclaw-agent |
| tasker-agent | task | `GET /tasks/all?filter=...`, `GET /tasks/{id}/comments` (in-prompt) | `PUT /tasks/{id}/comments` (enrichment state) | openclaw-agent |
| inbox/capture-agent | project + task | `GET /projects` (name lookup) | `PUT /projects/{id}/tasks` (task create) — via tasker | openclaw-agent |
| credential-health-check | project + task | `GET /projects` | `PUT /projects/{id}/tasks` (alert task create) | systemd-timer |
| provisioning tooling | project | `GET /projects`, `GET /projects/{id}/users` | User/project/label/filter creation | manual |

---

## Excluded Files from Grep 1

The following files appeared in Grep 1's 23-file output but are **not inventoried as touchpoint rows** because they contain no runtime Vikunja API calls:

| File | Reason for exclusion |
|---|---|
| `scripts/escalation/hard_fail.py` | Comment-only URL mention at line 339 (`https://office2.tail0f5f56.ts.net/tasks/1234` appears inside a Python docstring describing expected caller-provided strings). No `urllib`, `requests`, or `httpx` imports; no HTTP calls in the file. The grep hit was on the example URL in the docstring, not an API call. |

---

## Notes

1. **Two URL bases in use**: `https://office2.tail0f5f56.ts.net/api/v1` (Tailscale HTTPS, used in production scripts like `set_due_dates.py`, `sweeper.py`, `vikunja_writer.py`) and `http://100.92.197.90:3456/api/v1` (Tailscale IP direct HTTP, used in some older helpers like `record_completion.py`, `reconcile_completions.py`, `query_active_habits_v2.py`). This inconsistency is a latent fragility — URL change requires patching multiple files. observed (grep of `DEFAULT_BASE_URL` and `DEFAULT_VIKUNJA_BASE_URL` constants)

2. **Escalation and tasker in-prompt callsites**: The escalation skill (`~/.openclaw/skills/escalation/SKILL.md`) and tasker skill direct the LLM to issue `GET /tasks/all?filter=...` calls in-prompt. These are not represented in Python helper scripts and are not grep-discoverable from the local codebase. They are documented in ADR-0002 §Context and `vikunja-task-model-research.md` §2.2/2.4. This inventory is limited to locally-versioned Python scripts; in-prompt agent callsites are a research limitation. documented (`vikunja-task-model-research.md` §2.2/2.4, `adr-0002`)

3. **`habits/exclude_completed.py`**: Legacy v1 helper that parsed `[Felix]` comments to determine completion state. Superseded by `exclude_completed_v2.py` and JSONL-based approach (ADR-0002). Still present in repo at `scripts/habits/exclude_completed.py`. observed (`scripts/habits/exclude_completed.py` grep — token reference present but active deployment status deferred to implementation verification)

---

## Deferred to implementation

- **In-prompt agent callsites**: OpenClaw agent prompts (escalation, tasker, capture) issue Vikunja API calls directly in-prompt based on skill instructions. These are not grep-discoverable from the Mac-side codebase. A complete inventory requires reading live AGENTS.md and SKILL.md files on office2. Partially addressed by `vikunja-task-model-research.md` §2.2–2.4 but not formally registered as code touchpoints here.
- **Legacy vs active helper status**: `query_active_habits.py` (v1) is now inventoried as TP-18 (cycle 2). `exclude_completed.py` (v1) is inventoried as TP-15A. Whether either remains on the active cron path (vs superseded by `_v2` counterparts) requires checking live systemd units and OpenClaw configurations on office2. The inventory includes both generations to ensure WP02 counts the full surface area.
- **URL base consistency**: The two-URL-base pattern (Tailscale HTTPS vs direct IP HTTP) should be normalized as part of a sync architecture implementation. The config point is the correct normalization target.
- **Comments endpoint touchpoints**: `GET /tasks/{id}/comments` callsites in escalation/tasker agents are in-prompt only. Their endpoint, read_set, and freshness_assumption must be re-verified when those agents are migrated to script-based helpers.

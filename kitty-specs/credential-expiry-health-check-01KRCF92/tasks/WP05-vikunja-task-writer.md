---
work_package_id: WP05
title: Vikunja task writer
dependencies:
- WP02
requirement_refs:
- C-003
- C-006
- FR-004
- FR-006
- NFR-005
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T021
- T022
- T023
- T024
agent: "claude"
shell_pid: "23936"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/security/credential_health_check/vikunja_writer.py
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/vikunja_writer.py
- tests/security/test_vikunja_writer.py
tags: []
---

# WP05 — Vikunja task writer

## Objective

Implement the Vikunja-side of the dual-alert path: task creation with `due_date = boundary − 7 days`, Inbox project lookup, cross-reference to the GitHub issue. Cadence alerts only — activity-staleness alerts get GitHub issue only.

## Context

- **Spec** anchors: FR-006 (`due_date = boundary − 7 days`).
- **Contracts** anchor: `contracts/vikunja-task-writer.md` is the authoritative spec.
- **Plan** anchor: token at `/data/services/openclaw/secrets/vikunja-api` (C-006); stdlib `urllib.request` only (no `requests` dep).
- **Prior art**: `scripts/vikunja/setup_vikunja.py` and the `vikunja-api` OpenClaw skill cover call shape; the #112 date-timezone bug fix dictates ET-end-of-day for `due_date`.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main`.

## Subtasks

### T021 — Module skeleton: token loader + title/description templating

**Purpose**: Lay down the module and the pure-function bits (no network yet).

**Steps**:

1. Create `scripts/security/credential_health_check/vikunja_writer.py`:
   ```python
   from datetime import date, timedelta
   from pathlib import Path
   from .manifest import Credential

   VIKUNJA_API_BASE = "https://office2.tail0f5f56.ts.net/api/v1"   # confirm exact base in implementation
   VIKUNJA_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

   class VikunjaWriteError(Exception):
       pass

   def load_token() -> str:
       """Read the vikunja-api token from the office2 secrets path."""
       try:
           return VIKUNJA_TOKEN_PATH.read_text(encoding="utf-8").strip()
       except OSError as e:
           raise VikunjaWriteError(f"Could not read vikunja-api token at {VIKUNJA_TOKEN_PATH}: {e}")

   def task_title(credential: Credential) -> str:
       return f"Rotate credential: {credential.name}"

   def task_description(credential: Credential, boundary: date, github_issue_number: int) -> str:
       url = f"https://github.com/kentonium3/kg-automation/issues/{github_issue_number}"
       return (
           f"Rotate this credential, then close the linked GitHub issue and mark this task done.\n\n"
           f"GitHub issue: {url}\n\n"
           f"Cadence boundary (the actual deadline): {boundary.isoformat()}\n"
           f"This task is due one week earlier so the escalation engine pings before the boundary.\n\n"
           f"Stored at: {credential.storage}\n"
           f"Rotation procedure (full text in the GitHub issue body): see expiry_notes in credential-manifest.json."
       )

   def due_date_for_boundary(boundary: date) -> date:
       return boundary - timedelta(days=7)
   ```
2. Verify the Vikunja API base URL during implementation by checking an existing kg-automation script (`scripts/vikunja/setup_vikunja.py` or similar).

**Files**: `scripts/security/credential_health_check/vikunja_writer.py` (create skeleton).

---

### T022 — `lookup_inbox_project_id()`

**Purpose**: Find the Inbox project in Vikunja.

**Steps**:

1. Implement:
   ```python
   import urllib.request, json

   def lookup_inbox_project_id(token: str) -> int:
       req = urllib.request.Request(
           f"{VIKUNJA_API_BASE}/projects",
           headers={"Authorization": f"Bearer {token}"},
           method="GET",
       )
       try:
           with urllib.request.urlopen(req, timeout=10) as resp:
               projects = json.load(resp)
       except (urllib.error.URLError, json.JSONDecodeError) as e:
           raise VikunjaWriteError(f"Could not list Vikunja projects: {e}")
       inbox = [p for p in projects if p.get("title") == "Inbox"]
       if not inbox:
           raise VikunjaWriteError("Vikunja Inbox project not found by title=='Inbox'.")
       return min(p["id"] for p in inbox)  # smallest ID if multiple (defensive)
   ```
2. Cache the lookup per-process: store the result on a module-level variable after first call. The orchestrator runs once per cycle so the cache only matters within a single cycle, but it cleanly avoids redundant API calls if any.

**Files**: `scripts/security/credential_health_check/vikunja_writer.py` (modify).

---

### T023 — `create_task(credential, boundary, github_issue_number)`

**Purpose**: Actually create the task and return its ID.

**Steps**:

1. Implement:
   ```python
   from datetime import datetime, timezone

   def create_task(credential: Credential, boundary: date, github_issue_number: int) -> int:
       token = load_token()
       project_id = lookup_inbox_project_id(token)
       due = due_date_for_boundary(boundary)
       # Vikunja expects ISO-8601 datetime; use end-of-day ET to match #112's resolution.
       # Construct in ET timezone explicitly (use zoneinfo from stdlib, available 3.9+).
       from zoneinfo import ZoneInfo
       et_eod = datetime(due.year, due.month, due.day, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))
       due_iso = et_eod.isoformat()

       payload = {
           "title": task_title(credential),
           "description": task_description(credential, boundary, github_issue_number),
           "due_date": due_iso,
       }
       data = json.dumps(payload).encode("utf-8")
       req = urllib.request.Request(
           f"{VIKUNJA_API_BASE}/projects/{project_id}/tasks",
           headers={
               "Authorization": f"Bearer {token}",
               "Content-Type": "application/json",
           },
           data=data,
           method="PUT",   # Vikunja's "create task in project" is PUT — confirm during implementation.
       )
       try:
           with urllib.request.urlopen(req, timeout=15) as resp:
               body = json.load(resp)
       except urllib.error.HTTPError as e:
           raise VikunjaWriteError(f"Vikunja task create failed: HTTP {e.code} — {e.read().decode('utf-8', 'ignore')[:200]}")
       except (urllib.error.URLError, json.JSONDecodeError) as e:
           raise VikunjaWriteError(f"Vikunja task create network/parse error: {e}")
       return body["id"]
   ```
2. Verify the exact endpoint + HTTP verb during implementation against `scripts/vikunja/setup_vikunja.py`. PUT vs POST matters; the Vikunja API uses PUT for create-task-in-project in recent versions.

**Files**: `scripts/security/credential_health_check/vikunja_writer.py` (modify).

---

### T024 — Tests for vikunja_writer

**Purpose**: Exercise the writer paths with stubbed API.

**Steps**:

1. Create `tests/security/test_vikunja_writer.py`.
2. Pure-function tests (no mocking needed):
   - `test_due_date_for_boundary_subtracts_7_days`: `boundary=date(2027, 5, 11)` → `date(2027, 5, 4)`.
   - `test_task_title_format`: against fixture Credential.
   - `test_task_description_includes_github_link`.
3. Token-load tests (use `tmp_path` fixture from pytest):
   - `test_load_token_reads_file`: write a token to a tmp file, monkey-patch `VIKUNJA_TOKEN_PATH`, verify it's read and stripped.
   - `test_load_token_raises_on_missing_file`.
4. API tests (mock `urllib.request.urlopen` returning a context manager whose `read()` returns crafted JSON):
   - `test_lookup_inbox_project_returns_smallest_id_when_multiple`.
   - `test_lookup_inbox_project_raises_when_missing`.
   - `test_create_task_sends_expected_payload` — assert the `data` field of the constructed Request includes the title, description, and due_date in ET-EOD ISO-8601 form.
   - `test_create_task_handles_http_error` — stub raises `HTTPError`, function raises `VikunjaWriteError`.

**Files**: `tests/security/test_vikunja_writer.py` (create, ~140 lines).

---

## Definition of Done

- All four subtasks complete.
- `python -m pytest tests/security/test_vikunja_writer.py -v` → all green.
- `due_date` rendering uses `zoneinfo` for `America/New_York` end-of-day per the #112 lessons.
- Commit prefix: `feat(security):` or `feat(WP05):` referencing #115.

## Risks

- **Vikunja API endpoint/verb**: confirm against an existing script before committing the URL pattern. Wrong HTTP verb = silent 404 or surprise.
- **Token handling**: never log the token. The `load_token()` returns it; downstream callers must not pass it to logging methods. NFR-006.
- **Timezone**: Vikunja's date-handling regression in #112 was specifically about timezone interpretation; this WP uses `zoneinfo("America/New_York")` explicitly to match.

## Reviewer guidance

- Verify: `due_date_for_boundary` arithmetic is correct (`-7 days`, not `-1 week` calendar-arithmetic — both work for 7-day spans but explicit is better).
- Verify: token loading raises a typed error on failure, never returns an empty string silently.
- Verify: the constructed `Request` payload has `due_date` as a string, not a `date` object — JSON serialization needs the ISO form.
- Verify: no token, no PII, no credential value is included in any log statement in this module.

## Suggested implement command

```bash
spec-kitty agent action implement WP05 --agent <name>
```

## Activity Log

- 2026-05-11T22:05:39Z – claude – shell_pid=23611 – Started implementation via action command
- 2026-05-11T22:07:25Z – claude – shell_pid=23611 – 16/16 tests pass; 96 cumulative.
- 2026-05-11T22:07:29Z – claude – shell_pid=23936 – Started review via action command
- 2026-05-11T22:07:35Z – claude – shell_pid=23936 – Review passed: PUT verb correct, ET timezone, stdlib-only, token-never-logged.

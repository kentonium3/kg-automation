# Contract: Per-Touchpoint Migration Pattern

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

Every migrated touchpoint follows the same six-step pattern. This contract anchors the pattern so the implementer (and the reviewer) can verify a migration's correctness at a glance, and so all six in-scope files end up with structurally similar shapes.

---

## The pattern (six steps)

For each touchpoint file `scripts/<domain>/<filename>.py`:

### Step 1 — Identify the direct-Vikunja-read code

The implementer locates the existing direct-read code path. Typical patterns:

- A `_http_request("GET", url, token)` call (using `scripts.habits.record_completion._http_request` or a near-clone)
- A loop over Vikunja's paginated `GET /projects/<id>/tasks` endpoint
- A single-task `GET /tasks/<id>` call

These are deleted in the same change set that introduces the cache read.

### Step 2 — Add the canonical imports

At the top of the touchpoint file, add:

```python
from scripts.common.sync_cache import (
    read_cached_tasks,
    read_cached_task_by_id,
    read_completion_timestamps,  # only TP-02, TP-10, TP-12
    SLA_NORMAL,
    SLATier,
)
```

The exact set of imports depends on which helper functions the touchpoint uses. TPs that don't need `done_at` derivation omit `read_completion_timestamps`.

### Step 3 — Define the touchpoint's SLA constant

Add a module-level constant:

```python
TOUCHPOINT_SLA: SLATier = SLA_NORMAL
TOUCHPOINT_NAME = "<domain>.<filename_stem>"  # e.g., "habits.morning_checkin_list"
```

The `TOUCHPOINT_SLA` is the canonical per-callsite SLA assignment from `research.md` § Unknown 1. All 6 in-scope touchpoints land on `SLA_NORMAL` in this mission. The `TOUCHPOINT_NAME` is used in error messages so operator stderr identifies the failing callsite.

### Step 4 — Replace the read call

The direct-Vikunja-read call is replaced with a single helper invocation:

**Before** (pseudo-typical):

```python
token = _read_token(Path("/data/services/openclaw/secrets/vikunja-api"))
status, raw = _http_request("GET", api_base_url + "tasks/all", token)
tasks = raw  # list of dicts
for task in tasks:
    if task["done"] == False and "x" in task["title"]:
        # process
        ...
```

**After**:

```python
cached_tasks = read_cached_tasks(
    sla=TOUCHPOINT_SLA,
    touchpoint_name=TOUCHPOINT_NAME,
)
for task_id, view in cached_tasks.items():
    if view.is_private:
        continue  # private-project task — skip (see EC-7 below)
    if not view.fields.get("done") and "x" in view.fields.get("title", ""):
        # process; view.fields is the task's data
        ...
```

For `read_cached_task_by_id` (single-task lookups, TP-02, TP-10):

```python
view = read_cached_task_by_id(
    task_id=desired_id,
    sla=TOUCHPOINT_SLA,
    touchpoint_name=TOUCHPOINT_NAME,
)
# `view.fields["done"]` is the cached boolean
# `view.vikunja_updated_at` is the per-task timestamp
```

For touchpoints needing `done_at` (TP-02, TP-10, TP-12):

```python
ts = read_completion_timestamps(
    domain="habits",  # or "escalation" / "enrichment"
    task_id=desired_id,
    state_log_dir=Path("/data/services/openclaw/state"),
)
# ts.most_recent_complete_at_utc, ts.most_recent_complete_date_et
```

### Step 5 — Let `OSError` propagate

The touchpoint MUST NOT catch the helper's `OSError` and convert it to anything except a non-zero exit. Typical shape:

```python
def main() -> int:
    try:
        cached_tasks = read_cached_tasks(
            sla=TOUCHPOINT_SLA,
            touchpoint_name=TOUCHPOINT_NAME,
        )
    except OSError as e:
        print(f"[{TOUCHPOINT_NAME}] {e}", file=sys.stderr)
        return 3  # validation_error per the sync driver's convention
    # ... rest of touchpoint logic
    return 0
```

Some touchpoints already have a `try/except OSError` block that handles direct-Vikunja-read failures (e.g., `_http_request` raising on HTTP 503). That block is reused for cache-read failures with the message format updated.

### Step 6 — Delete the direct-read code

After verifying the cache-read path works (test pass), the implementer DELETES:

- The `_http_request` helper if it was inlined per-touchpoint (some touchpoints copy `record_completion.py:_http_request` verbatim)
- The Vikunja URL constants used only for the deleted GETs
- The `vikunja-api` token-read code if the touchpoint had no other Vikunja write path
- Any import of `urllib.request` if it was used only for the deleted GETs

Touchpoints that retain write paths (e.g., `set_due_dates.py` keeps its PUT phase) KEEP their existing `_http_request` + token-read + URL constants for the write side. The implementer deletes ONLY the read-side code.

**Verification**: `grep -E 'urlopen|_http_request.*GET' scripts/<domain>/<filename>.py` returns zero hits AFTER the migration. This is part of the WP's DoD per FR-006 + NFR-006.

---

## Edge cases per the pattern

**EC-1 — Touchpoint that enumerates "all active tasks" (e.g., TP-03)**

```python
cached_tasks = read_cached_tasks(sla=TOUCHPOINT_SLA, touchpoint_name=TOUCHPOINT_NAME)
active_tasks = [
    view
    for view in cached_tasks.values()
    if not view.is_private  # skip private
    and not view.fields.get("done")  # active = not done
    and view.fields.get("project_id") == HABITS_PROJECT_ID
]
```

**EC-2 — Touchpoint that looks up a single task (e.g., TP-04 GET phase)**

```python
view = read_cached_task_by_id(
    task_id=task_id,
    sla=TOUCHPOINT_SLA,
    touchpoint_name=TOUCHPOINT_NAME,
)
# read_cached_task_by_id raises if the task is missing or private
```

**EC-3 — Touchpoint that reconciles cache against state log (TP-02)**

```python
for task_id in habit_task_ids:
    cached_view = read_cached_task_by_id(task_id, sla=TOUCHPOINT_SLA, touchpoint_name=TOUCHPOINT_NAME)
    completion_ts = read_completion_timestamps(
        domain="habits",
        task_id=task_id,
        state_log_dir=STATE_LOG_DIR,
    )
    if cached_view.fields["done"] is True and completion_ts.most_recent_complete_at_utc is None:
        # Vikunja says done but no completion event in state log — operator-side completion happened
        # ... existing reconciler logic
```

**EC-7 — Private-project tasks in bulk enumeration**

For `read_cached_tasks` enumeration, the touchpoint MUST check `view.is_private` and skip those entries. The helper does NOT skip them in the bulk return because some touchpoints may legitimately want to enumerate IDs even for private tasks.

For `read_cached_task_by_id`, the helper raises `OSError` on private — the touchpoint propagates per step 5.

---

## What the migration pattern explicitly does NOT do

- Does NOT introduce per-touchpoint config flags
- Does NOT introduce a cache-vs-direct toggle
- Does NOT introduce backward-compatibility code paths
- Does NOT change the touchpoint's CLI surface, exit codes (beyond reusing 3 for validation_error), or stderr semantics
- Does NOT touch any AGENTS.md prompt (per spec A-6)
- Does NOT update the touchpoint's docstring's "fetches from Vikunja" wording — wait, it DOES update that wording. New wording: "reads from the sync cache at /data/services/openclaw/state/sync/task-cache.json (see scripts/common/sync_cache.py for the canonical entry point)." This is a small but real change; the implementer makes it.

---

## Reviewer checklist (per-WP)

For each touchpoint a WP migrates, the reviewer verifies:

- [ ] `grep -E 'urlopen.*GET|_http_request.*GET' <file>` returns zero hits
- [ ] `grep -E 'import urllib' <file>` either absent or used only for write-side calls (annotated)
- [ ] `from scripts.common.sync_cache import` line exists with the expected imports
- [ ] `TOUCHPOINT_SLA = SLA_NORMAL` (or another tier with `research.md` justification)
- [ ] `TOUCHPOINT_NAME = "<domain>.<filename_stem>"` matches the file
- [ ] OSError from `read_cached_*` propagates to a non-zero exit (no swallowing)
- [ ] Tests use `mock_sync_cache_fixture` (no `mock_urlopen` for the read path)
- [ ] Tests cover: cache-missing (raises), stale (raises), task-not-found if applicable (raises), private (raises), happy path (returns expected result)
- [ ] Touchpoint docstring updated to mention cache reads instead of direct Vikunja

---

## What this contract does NOT cover

- The shape of the touchpoint's downstream logic post-read (that's per-touchpoint and per-WP)
- The exact error-message wording from non-helper sources (e.g., a touchpoint may surface its own errors for non-cache failures)
- How the touchpoint integrates with its OpenClaw agent prompt (per A-6: unchanged)

# Data Model

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Phase**: 1 (design)

No data model changes — this mission is a behavior fix in a Python helper. No schema changes, no JSONL state-log changes, no new entities.

This document maps the code surface that changes (BEFORE/AFTER) in `scripts/habits/query_active_habits_v2.py`.

---

## Entity 1 — `query_active_habits_v2.py` function map

### BEFORE (pre-mission, ~line 172-243)

```python
def _build_filter_expression(today: str) -> str:
    """Build the Vikunja native filter expression for active-today habits."""
    return f"due_date <= {today}T23:59:59Z AND done = false"


def query_active_today(api_base_url, token, today=None) -> list[dict]:
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(...)
    project_id = _resolve_habits_project_id(api_base_url, token)
    filter_expr = _build_filter_expression(today_date)
    query = urllib.parse.urlencode({"filter": filter_expr})
    url = _join_url(api_base_url, f"projects/{project_id}/tasks?{query}")
    _status, payload = _http_get(url, token)
    ...
    return out  # All tasks returned by Vikunja (relies on server-side filter)
```

### AFTER (post-mission)

```python
# _build_filter_expression is REMOVED entirely.
# urllib.parse import may also be REMOVED if no other callers (verify during impl).


def query_active_today(api_base_url, token, today=None) -> list[dict]:
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(...)
    project_id = _resolve_habits_project_id(api_base_url, token)
    url = _join_url(api_base_url, f"projects/{project_id}/tasks")  # NO ?filter=
    _status, payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(...)

    # Client-side filter — mirror reconcile_completions.py pattern.
    boundary = f"{today_date}T23:59:59Z"
    out: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("done", False):
            continue
        due = item.get("due_date") or ""
        # Skip tasks with no due_date OR a due_date past the boundary.
        if not due or due > boundary:
            continue
        out.append(item)
    return out
```

**Filter logic notes**:
- `done == True` → exclude.
- `due_date` empty or `"0001-01-01T..."` (Vikunja's "unset" placeholder) → exclude (no due date means not "due today").

  **Wait**: the smoke-test session log shows habits being returned with `due_date: "0001-01-01T00:00:00Z"` and the v1 path still treated them as active. The v2 server-side filter would have EXCLUDED them (since `0001-01-01 <= 2026-05-19` is true; they'd be included by the server filter). Actually `0001-01-01 <= today` IS true. So a literal port of the server-side semantics would INCLUDE these.

  **Adjustment**: skip the "not due" check. The Vikunja server-side filter `due_date <= now/d` evaluates `0001-01-01T00:00:00Z <= today` as TRUE (the unset-date is lexicographically less than today). So the client-side filter must do the same: empty-string `due_date` is excluded, but `"0001-01-01T00:00:00Z"` is included via the `<=` lex compare.

  **Final logic**: `if due and due <= boundary` → include. (Where empty string is the only "skip" sentinel.) The current v2 code at line 244 returns items where `isinstance(item, dict)` — no due-date check at all. Server-side filter handled it. New code must replicate that.

- `due_date <= today + 23:59:59Z` (lex compare with the ISO-8601 string) → include.

### Comparison with `reconcile_completions.py` (the reference pattern)

`reconcile_completions.py` lines 188-193 use:
```python
url = _join_url(api_base_url, f"projects/{project_id}/tasks")  # No filter param
_status, payload = _http_get(url, token)
# Then iterate payload and filter in Python.
```

Same shape. The new `query_active_today` adopts this verbatim.

---

## Entity 2 — Test file (NEW)

```
tests/habits/test_query_active_habits_v2_filter.py  (~50 lines, 5 test cases)
```

Test cases per research.md D4:
1. Happy path — mixed task states, returns only the active-today task.
2. All tasks done — empty list.
3. All tasks future — empty list.
4. Date boundary `==` — included.
5. HTTP 400 on the new URL — raises OSError (existing behavior).

Mocks: `unittest.mock.patch` on `_http_get` (the private HTTP helper).

---

## Entity 3 — `vikunja-task-model-research.md` G7 entry (NEW)

Append G7 to the existing Verified API Gotchas appendix per research.md D5. Format matches G1-G6 entries.

---

## Out of scope (no entities affected)

- No changes to `meta.json`, `status.events.jsonl`, or any mission-state files (workflow-managed).
- No changes to `scripts/common/state_log.py` (the JSONL substrate).
- No changes to AGENTS.md (already hotfixed in commit `4e7177c`).
- No changes to cron entries (`~/.openclaw/openclaw.json`).
- No changes to the helper's CLI surface (no new flags, no renames).

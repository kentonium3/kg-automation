# Contract: enumerate_candidates CLI (IC-02)

**Module**: `scripts/escalation/enumerate_candidates.py`
**Invocation**: `cd /home/claude/kg-automation && python3 -m scripts.escalation.enumerate_candidates [--date YYYY-MM-DD]`
(`--date` defaults to today America/New_York; `--base-url`/`--token-path` exist for local testing.)

## Behavior
1. Paginate `VikunjaClient().get("/tasks/all", params={"page": n, "per_page": 50})` until an empty batch.
2. Filter client-side per escalation §1 (R3), using `vikunja_scope.get_escalation_excluded_project_ids()`.
3. Emit a JSON array of EscalationCandidate objects on stdout, sorted deterministically (e.g. by `due_date`, then `task_id`).

## stdout (success)
```json
[{"task_id": 123, "project_id": 5, "title": "…", "due_date": "2026-07-10T00:00:00Z", "priority": 3, "reason": "overdue"}]
```
Empty candidate set → `[]` on stdout, exit 0.

## Exit codes
- `0` — success (including empty result).
- `1` — Vikunja unreachable / HTTP error (agent surfaces a truthful failure; does NOT fabricate).
- `3` — usage/validation error.

## Tests (tests/escalation/test_enumerate_candidates.py) — fake VikunjaClient, no network
- Overdue qualifies; due-today+priority>=3 qualifies; due-today+priority<3 does NOT.
- `priority < 2` excluded; excluded project ids excluded (driven by scope config).
- Null-due sentinel excluded; `done=true` excluded.
- Pagination: stops on empty batch, not on `len < 100` (multi-page fixture).
- Vikunja error → exit 1, nothing on stdout.
- Filter reads excluded ids from `vikunja_scope` (swap the config → different result).

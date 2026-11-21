# Contract: VikunjaClient v2 seam (`scripts/common/vikunja_client.py`)

Server reference: vikunja-harness `d7e202228`. See `research.md` R-001…R-004.

## Construction

The existing constructor and validation are unchanged. `base_url` must match `^https?://[^/]+/api/v1$`.
The new read-only attribute is `v2_base_url = base_url[:-len("/api/v1")] + "/api/v2"`.

## Methods

```python
def patch_task(self, task_id: int, changes: Mapping[str, Any]) -> dict | None:
    """PATCH /api/v2/tasks/{id}, Content-Type application/merge-patch+json.
    - ValueError if changes is empty, contains a None value, or contains a key
      outside WRITABLE_TASK_FIELDS.
    - Returns the response task dict on 200, None on 304 (unchanged).
    - Raises the existing VikunjaError subclasses on other statuses.
    """

def end_series(self, task_id: int) -> dict:
    """Resumable, idempotent series end (data-model.md 'End-series recovery
    contract'). Works from a fresh read; PATCH {"repeat": null} then
    PATCH {"done": true}, each followed by a readback. Never combines both
    keys in one call (R-001 hazard 3). Returns the final task, verified
    done=true AND no rule in every branch (a done task that still has a
    rule gets PATCH {"repeat": null} and a readback; done is unchanged so
    it does not reopen).
    Raises SeriesEndIncomplete(task_id, state) on partial progress
    ("rule_cleared_not_done", "rule_reappeared"); on timeout it re-reads
    before deciding. Tests: failure and timeout at each step, 304 on each,
    rule reintroduced between steps, already-ended task.
    """

def get_task_v2(self, task_id: int) -> dict: ...

def create_task_v2(self, project_id: int, fields: Mapping[str, Any], *,
                   rrule: str | None = None,
                   initial_due_time: str | None = None) -> dict:
    """POST /api/v2/projects/{id}/tasks. Sends repeats_rrule when rrule is given.
    Does NOT verify; the caller asserts same_rule(created, expected)."""

def occurrences(self, task_id: int, *, count: int = 1) -> dict:
    """GET /api/v2/tasks/{id}/occurrences?count=N (1..100).
    401 → VikunjaAuthError with a message naming the missing
    tasks.occurrences permission."""

def preview_occurrences(self, *, rrule: str | None = None,
                        repeat: Mapping | None = None,
                        due_date: str | None = None,
                        initial_due_time: str | None = None,
                        timezone: str = "America/New_York",
                        repeats_from_current_date: bool = False,
                        count: int = 3) -> dict:
    """POST /api/v2/tasks/occurrences/preview. Exactly one of rrule/repeat and
    one of due_date/initial_due_time (ValueError otherwise, before any call).
    400 code 2002 → VikunjaBadRequestError (invalid rule); 2003 → invalid tz.
    401 → VikunjaAuthError naming tasks.occurrences_preview."""
```

**Removed:** `replace_task_fields`. Callers move to `patch_task`. It is removed only once its last caller (IC-02, IC-04 or IC-07) has moved, in the final client WP step.

**Kept:** `update_task_fields`, as the v1 full-echo fallback. It has no planned caller. It changes as follows (post-plan review finding 10):

- It calls `self.post(f"/tasks/{id}", json=merged)` directly.
- It gains a **guard**. If the current task has a rule, `repeats_from_current_date=true` or reminders, and `changes` would drop or alter them, it raises `ValueError` unless `allow_rule_change=True`.
- Tests cover a full-echo success with a new-shape body, refusal of a destructive change, and the explicit override.

`WRITABLE_TASK_FIELDS = {title, description, done, due_date, repeat, repeats_rrule, repeats_from_current_date, priority, start_date, end_date, hex_color, percent_done, project_id, reminders, is_favorite}`. This follows the fork's column list (`tasks.go:1518-1533`), excluding `bucket_id` and `cover_image_attachment_id`, which Felix does not use.

## `scripts/common/vikunja_rule.py` (pure)

```python
def normalise(repeat: Mapping | None) -> dict | None
def same_rule(a: Mapping | None, b: Mapping | None) -> bool
def has_rule(task: Mapping) -> bool
def completion_outcome(before: Mapping, after: Mapping) -> Literal["advanced", "series_ended", "unexpected"]
def rrule_text_to_parts(text: str) -> dict      # for schedule/inventory comparisons; no network
def parts_to_rrule_text(parts: Mapping) -> str
```

## Test obligations (FR-020, NFR-002)

For each write site, a test drives the real call path with `mock_vikunja_urlopen` serving a new-shape task: rule, `repeats_from_current_date=true`, and one reminder. It asserts that:

- the PATCH body contains only the intended keys,
- no `null` is sent,
- the site's post-write check passes on an intact rule and **fails** when the fake server returns the task with the rule stripped (the same-fixture positive control).

Invariants are per operation, following data-model.md. Completion sites also test COUNT=2→1 (advanced, rule differs only in COUNT), COUNT=1→Done with no rule (expected end), UNTIL passed (ended, rule kept), and Done without expected exhaustion (unexpected, alert). Reminder tests tell server-driven movement of relative reminders apart from accidental removal.

Each test is shown failing against the pre-fix code, with the evidence recorded in the WP.

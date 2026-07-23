---
affected_files: []
cycle_number: 1
mission_slug: retire-vikunja-felix-bot-01KY829X
reproduction_command:
reviewed_at: '2026-07-23T22:53:11Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
review_artifact_override_at: "2026-07-23T23:00:46Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP02"
review_artifact_override_reason: "Review passed (opus, cycle 2): task-page non-JSON-2xx parity restored; 236 tests pass. --skip-review-artifact-check per known spec-kitty #1817 (stale cycle-1 rejection artifact blocks cycle-2 approve)."
---

# WP02 review feedback — cycle 1/3 (REJECT)

The migration is excellent and nearly complete — enumeration preservation, `http.py` retirement,
`cycle.py` untouched, timeout preserved, `{}`-vs-`None` closed at the pagination guard, scope clean,
236 sync tests pass. **One real behavior-preservation defect must be fixed before approval.**

## Defect — non-JSON 2xx body on a per-project task page changes behavior (fetch.py)

**File**: `scripts/sync/fetch.py`, the per-project task-page loop (~lines 185-193), plus the false
parity justification at ~lines 258-266 and the test `test_per_project_tasks_non_json_body_raises_parse_error`
(Scenario 12) in `tests/sync/test_fetch.py`.

**The regression**:
- **Pre-migration**: `get_json(...)` returned `None` for a non-JSON 2xx task-page body
  (`_http_request` returned `(200, None)` on `json.loads` failure). The next line
  `if tasks_raw is None: break` fired **first** → that project's pagination **silently ended with
  NO error / NO `cycle_error`**. It never reached the `isinstance(list)` → `parse_error` check.
- **Post-migration**: `client.get(...)` raises `VikunjaServerError(status=200)` →
  `except VikunjaError` → `_classify_vikunja_error` → `parse_error` → **the whole cycle aborts.**
- This violates FR-003 (behavior-preserving) and SC criterion 6 (cycle_error tokens unchanged for
  every error class): old = silent break / no token; new = `parse_error` abort.

**Why the current justification is wrong**: the comments at `fetch.py:258-266` and the Scenario 12
test claim "net classification unchanged (None → fails isinstance(list) check → parse_error)". That
is true **only for the `/projects` call**. For a **task page**, `None` hit `is None: break` and
**never reached** the `isinstance(list)` check — so "net classification unchanged" is false there.

## Required fix — option A (strict Phase-1 parity)

This mission is strictly behavior-preserving (FR-003, C-001), so preserve the old behavior exactly —
do NOT introduce the fail-loud abort:

1. In the per-project task-page loop (`fetch.py:185-193`), treat a **non-JSON 2xx body as
   page-exhausted** to match the old silent break — e.g. catch `VikunjaServerError` with
   `status == 200` inside the loop and `break` (page done), rather than letting it propagate to
   `_classify_vikunja_error`/`parse_error`. No new `cycle_error` may be emitted on this path.
2. **Only** the task-page path changes — leave the `/projects` call's non-JSON-2xx → `parse_error`
   mapping as-is (that one genuinely is unchanged).
3. Update the Scenario 12 test (`test_per_project_tasks_non_json_body_raises_parse_error`) to assert
   the **corrected** behavior: a non-JSON 2xx task-page body ends that project's pagination with no
   error (page-exhausted), matching pre-migration. Rename it accordingly.
4. Correct the now-accurate wording in the `fetch.py:258-266` comment so it no longer claims the
   task-page path is "net unchanged" via the isinstance check.

Do NOT change any other classification — `auth_failure` (401/403), `vikunja_5xx`,
`vikunja_unreachable` (400/404/other-4xx/network/timeout), `/projects` `parse_error`, `/info`
best-effort swallow, empty-response cache-abort, dedup, and null/`{}` page terminators are all
confirmed correct and must stay as-is.

## After fixing
- Re-run `python3 -m pytest tests/sync/ -q` (all green) and the diff-scoped flake8 (exit 0).
- Commit in the lane worktree with a scoped add; do NOT run `move-task` (orchestrator handles it
  from primary per #710). Report the change + test results back.

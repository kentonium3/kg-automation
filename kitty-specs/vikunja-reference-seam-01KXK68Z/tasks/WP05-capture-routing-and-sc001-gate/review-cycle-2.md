---
affected_files: []
cycle_number: 2
mission_slug: vikunja-reference-seam-01KXK68Z
reproduction_command:
reviewed_at: '2026-07-15T20:42:20Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

# WP05 Review — Cycle 1 — REQUEST_CHANGES (reviewer: codex, gpt-5-codex)

The routing rework, graceful attach-fallback, and AGENTS.md are all correct. The
SC-001 grep gate — the mission capstone — is too narrow and, because of that, let a
real runtime violation slip through. Two-part fix:

1. **Broaden the SC-001 Class-B (hardcoded-id) detector + positive controls.**
   It currently only catches `NAME = <int>` (e.g. `HABITS_PROJECT_ID = 13`). It
   MUST also catch hardcoded project-id / label-id resolution targets in these forms:
   - typed assignments: `DEFAULT_TARGET_PROJECT_ID: int = 13`
   - container literals: `PROJECT_IDS: list[int] = [13]`, `frozenset({13})`, `{13}`
   - dict fields used as resolution targets: `{"project_id": 13}`, `{"label_id": 23}`
   Add a positive-control test for EACH new form (proving the gate FAILS when each is
   introduced into a runtime file), plus keep the coverage-guard test so the gate
   can't silently become a no-op.

2. **Fix the real violation the broadened gate now surfaces (no vestiges, FR-005).**
   `scripts/enrichment/reconcile_completions.py:153` —
   `EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({13})` hardcodes the Habits
   project id in a runtime Felix module (it was missed in the original FR-005
   inventory). Migrate it onto the seam exactly like `vikunja_scope`'s escalation
   exclusion: derive from the accessor, e.g.
   `EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({vikunja_refs.project_id("habits")})`
   (delete the literal `13`; keep the frozenset shape + the `excluded_project_ids`
   param threading). Update its test (tests/escalation/test_reconcile_completions.py
   or wherever it lives) to assert the derived value. This is a justified out-of-map
   edit — WP05 owns the gate that requires the surface to be clean, and this is the
   no-vestiges completion of the migration; record the rationale.

**Do NOT over-broaden into false positives:** `scripts/habits/identify_workout_task.py:23`
(`{"task_id": 17, "title": "Workout", "project_id": 1, ...}`) is **example/sample
task data**, NOT a resolution target — the gate must not flag illustrative task
dicts. Distinguish "a dict field that IS the resolution target" from "sample task
data that happens to contain project_id". If your broadened Class-C dict rule would
flag the workout sample, scope it so it only fires on resolution-intent (e.g. a
module-level constant / default assigned from such a dict), not arbitrary sample data.

After the fix: `pytest tests/inbox/ tests/common/test_sc001_grep.py tests/escalation/ -q`
green, and the SC-001 grep green over the now-genuinely-complete surface.

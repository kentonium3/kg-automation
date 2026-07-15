---
affected_files: []
cycle_number: 3
mission_slug: vikunja-reference-seam-01KXK68Z
reproduction_command:
reviewed_at: '2026-07-15T20:57:30Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

# WP05 Review — Cycle 2 — REQUEST_CHANGES (reviewer: codex, gpt-5-codex)

The enrichment migration + broadened gate (single-line forms) are confirmed good.
Two remaining blocking issues:

1. **Broken import in the merged surface (must fix before merge).**
   `scripts/security/credential_health_check/orchestrator.py:36` imports
   `lookup_inbox_project_id` from `.vikunja_writer`, and calls it at lines **153**
   and **257** — but WP03 (T014) DELETED that helper. `pytest
   tests/security/test_orchestrator.py` fails at collection with
   `ImportError: cannot import name 'lookup_inbox_project_id'`. (WP03's review only
   ran `test_vikunja_writer.py`, so this consumer slipped through.)
   **Required (justified out-of-map, same class as the enrichment fix — completes
   FR-005 for a consumer the original inventory missed):** migrate the orchestrator
   to the seam. Drop `lookup_inbox_project_id` from the import; replace both call
   sites with `vikunja_refs.project_id("inbox")` (network-free — the old helper took
   a token for a live by-title lookup; the seam needs none, so remove the now-unused
   token argument/variable if it becomes dead). Run the FULL security suite
   (`pytest tests/security/ -q`), not just the writer test, to confirm nothing else
   references the deleted helper.

2. **SC-001 gate still misses MULTILINE hardcoded-id forms.**
   The scanner is line-based, so an assignment split across lines bypasses it, e.g.:
   ```python
   DEFAULT_TARGET = {
       "project_id": 13,
   }
   EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({
       13,
   })
   ```
   **Required:** make the detector multiline-robust. Prefer AST-based scanning
   (parse each runtime `*.py`, walk for: a module-level constant whose name contains
   PROJECT_ID/LABEL_ID assigned an int literal anywhere in its value — incl. inside
   list/set/frozenset/dict; and dict literals binding `"project_id"`/`"label_id"` to
   an int literal on an assignment RHS) — AST handles line breaks inherently and is
   less false-positive-prone. If you keep regex, normalize logical lines first.
   Add positive controls for the multiline dict form AND the multiline
   frozenset/container form (assert the gate FAILS on each). Keep all existing
   negative controls green (esp. the identify_workout_task sample-data case).

After: `pytest tests/security/ tests/inbox/ tests/common/test_sc001_grep.py tests/enrichment/ -q`
green, and the SC-001 gate green over the full surface with the multiline forms now covered.

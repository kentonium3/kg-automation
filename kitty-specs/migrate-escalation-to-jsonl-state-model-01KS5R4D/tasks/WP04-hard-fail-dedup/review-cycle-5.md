---
affected_files: []
cycle_number: 5
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T20:35:31Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
---

**Issue 1**: C-006 redaction is still incomplete for caller-provided fields added to `render_bug_body`.

`scripts/escalation/hard_fail.py` sanitizes `task_title`, `jsonl_path`, `detection_snippet`, `derive_state_error_message`, and string values from `vikunja_state`, but it interpolates two other caller-provided strings without redaction:

- `vikunja_url` is used raw in the Markdown link at `render_bug_body` lines 344-346.
- `detected_at` is assigned raw to `detected_at_repr` at line 350 and rendered in the body at line 363.

Because both values are function parameters and both are interpolated into the filed bug body, an adversarial caller can still leak `~/second-brain`, `/second-brain`, or `_private` through either field. This violates the cycle-1 requirement that C-006 redaction cover every caller-provided field that gets interpolated.

Fix: sanitize `vikunja_url` and `detected_at` before interpolation, or remove these optional caller-provided fields from the body surface if they are not needed. Add adversarial tests for both fields that assert the forbidden substrings are absent and `[REDACTED:second-brain-path]` appears.

---
affected_files: []
cycle_number: 4
mission_slug: felix-rrule-adaptation-01M7TKNX
reproduction_command:
reviewed_at: '2026-11-20T22:32:20Z'
reviewer_agent: claude
wp_id: WP10
---

# WP10: reopened for an independent approval (Kent approved option A, 2026-11-20)

Accept refused with REVIEW_NOT_INDEPENDENT: WP10's cycle-3 arbiter approval is not a confirmable independent review. The two cycle-3 Codex findings were deferred, so they must be fixed now, on this lane, before a fresh Codex review:

1. **Journal / torn-tail recovery must agree.** A complete JSON record without a trailing newline must be preserved (append the newline), not truncated. Add a multi-task resume regression in which the markdown report shows every repair's real outcome.
2. **Repeated --task-id.** Dedupe or reject repeated values before the selection is persisted. A later attempt must never replace a completed outcome. Add a CLI regression test.
3. **rule_inventory.py docstrings.** Two docstrings mention the retired repeat fields. WP08's ratchet (tests/architectural/test_no_retired_repeat_fields.py, on lane-h) will flag them once the lanes consolidate. Reword them; don't add an allowance.
4. **docs/runbooks/vikunja-task-repair.md vs the code.** The statuses table omits that --accept-changed also needs --task-id, and it doesn't say that emit's issue-comment.md mode is 600 only on create. Align the runbook with the code.

Keep it practical (Kent, 2026-11-20): fix these four. No new edge-case hardening.

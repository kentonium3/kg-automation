---
affected_files: []
cycle_number: 5
mission_slug: tasker-jsonl-migration-01KSB5XV
reproduction_command:
reviewed_at: '2026-05-23T21:28:49Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` now tells the raw `enrich_task` flow to run `record_completion.py` at Step 4 before sending the proposal. At that point no Vikunja task exists yet: the same flow creates the task only later in Step 6, and the delegation input only contains `raw_text` and `source_reference`, not a `task_id`. `record_completion.py` requires a valid `--task-id`, so the primary new-task action would fail or require fabricating an invalid id before Kent ever sees the proposal. Fix the standing orders so `record_completion.py --state proposed` is only used for flows that already have a Vikunja task id (`retroactive_enrichment` and `detect_incomplete`), while the raw `enrich_task` path preserves the existing proposal-then-create flow and records `confirmed` only after the task id exists. If the intended design is to create a staging Vikunja task before proposal, spell that out explicitly and update the flow/tests/docs accordingly, but do not leave the current impossible invocation.

**Issue 2**: WP03-owned operator/agent docs contradict the implemented `record_completion.py` soft-fail contract. `scripts/enrichment/record_completion.py` and the architecture data-flow docs say a post-Vikunja JSONL failure logs a warning and exits `0` per FR-013, while `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` says exit `2` is the JSONL soft-fail and `docs/runbooks/tasker-ops.md` troubleshooting repeats that exit `2` means JSONL soft-fail. As written, the tasker standing orders describe an error branch that will not run for the actual post-Vikunja soft-fail case. Align the WP03 docs with the implemented contract: exit `0` can include a `state_log_soft_fail` warning after Vikunja succeeds; exit `2` is reserved for pre-Vikunja/no-vikunja JSONL failures where no downstream side-effect landed.

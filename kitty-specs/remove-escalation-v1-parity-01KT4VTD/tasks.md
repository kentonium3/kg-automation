# Tasks: Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`
**Planning base**: `main` | **Merge target**: `main`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Remove v1 comment-write path + helpers + docstrings from `record_completion.py` | WP01 | | [D] |
| T002 | Remove phantom-subscription detector + helpers + docstrings from `reconcile_completions.py` | WP01 | [D] |
| T003 | Remove `phantom_subscription` reason code + comment-count template from `hard_fail.py` | WP01 | [D] |
| T004 | Delete `backfill_jsonl_from_comments.py` and `test_backfill.py` | WP01 | [D] |
| T005 | Update test suites: `test_record_completion.py`, `test_reconcile_completions.py`, `test_hard_fail.py` | WP01 | | [D] |
| T006 | Run full `pytest tests/escalation tests/enrichment` and confirm green | WP01 | | [D] |
| T007 | Strip v1 parity + phantom language from `SKILL.md`, `AGENTS.md`, `TOOLS.md` (felix-admin-escalation) | WP02 | [D] |
| T008 | Strip parity verification queries + phantom guidance from `escalation-ops.md` runbook | WP02 | [D] |
| T009 | Remove `escalation-event-write-vikunja` from `data-flows.json` + regen `data-flows.md` | WP02 | [D] |
| T010 | Strip v1 parity reference from `service-inventory.json` `felix-admin-escalation` entry + regen `service-inventory.md` | WP02 | [D] |
| T011 | Run `tooling/scripts/validate_docs.py` + final grep sweep across the codebase | WP02 | | [D] |

11 subtasks across 2 WPs. WP01 (code + tests) lands first to settle behavior; WP02 (prompts + runbook + arch-data) lands second so doc edits align with the behavior just shipped.

## Work Package WP01 — Code + tests cleanup

**Goal**: Delete every active code path that writes, reads, or templates `[Felix-Escalation]` substrate. Keep the JSONL substrate untouched. Verify via the existing test suite (extended for the new "no comment write, no phantom path" assertions).

**Priority**: P1 (foundational; WP02 depends on the behavior being settled)

**Independent test**: `pytest tests/escalation tests/enrichment -v` passes; `grep -rn '_format_v1_comment\|_COMMENT_PREFIX\|_COMMENT_MARKER\|_count_escalation_comments\|phantom_subscription' scripts/escalation/ tests/escalation/` returns zero matches.

**Estimated prompt size**: ~500 lines

### Included subtasks

- [x] T001 Remove v1 comment-write path + helpers + docstrings from `record_completion.py` (WP01)
- [x] T002 Remove phantom-subscription detector + helpers + docstrings from `reconcile_completions.py` (WP01)
- [x] T003 Remove `phantom_subscription` reason code + comment-count template from `hard_fail.py` (WP01)
- [x] T004 Delete `backfill_jsonl_from_comments.py` and `test_backfill.py` (WP01)
- [x] T005 Update test suites: `test_record_completion.py`, `test_reconcile_completions.py`, `test_hard_fail.py` (WP01)
- [x] T006 Run full `pytest tests/escalation tests/enrichment` and confirm green (WP01)

### Dependencies

None.

## Work Package WP02 — Prompts + runbook + architecture data cleanup

**Goal**: Update every non-code surface that referenced the v1 parity behavior or the phantom-subscription detection. Agent prompts, runbook queries, machine-readable architecture data, and the markdown views derived from that data.

**Priority**: P1 (paired with WP01; must land in the same merge so deployed agent prompts match deployed code behavior)

**Independent test**: `tooling/scripts/validate_docs.py` passes; final grep sweep across `scripts/openclaw/`, `docs/runbooks/`, `docs/design/architecture/data/` returns zero matches for the parity/phantom terms.

**Estimated prompt size**: ~400 lines

### Included subtasks

- [x] T007 Strip v1 parity + phantom language from `SKILL.md`, `AGENTS.md`, `TOOLS.md` (felix-admin-escalation) (WP02)
- [x] T008 Strip parity verification queries + phantom guidance from `escalation-ops.md` runbook (WP02)
- [x] T009 Remove `escalation-event-write-vikunja` from `data-flows.json` + regen `data-flows.md` (WP02)
- [x] T010 Strip v1 parity reference from `service-inventory.json` `felix-admin-escalation` entry + regen `service-inventory.md` (WP02)
- [x] T011 Run `tooling/scripts/validate_docs.py` + final grep sweep across the codebase (WP02)

### Dependencies

- **WP01** — code behavior must be settled before doc/prompt edits describe the new behavior. WP02 cannot start until WP01 is `approved`.

## Branch strategy

- Planning base: `main`
- Merge target: `main`
- Execution worktrees: created by `spec-kitty next` per `lanes.json`. Two WPs may share one lane (sequential by dependency) or land in distinct lanes (parallel-eligible after WP01 approval).

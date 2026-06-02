# Implementation Plan: Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`
**Branch**: `main` (planning + merge target) | **Date**: 2026-06-02
**Spec**: [spec.md](spec.md) | **Source issue**: [#376](https://github.com/kentonium3/kg-automation/issues/376)

## Branch Strategy

- Current branch at plan start: `main`
- Planning/base branch: `main`
- Final merge target: `main`
- `branch_matches_target`: true

## Summary

Single-mission cleanup that completes the #309 escalation → JSONL migration by removing every transitional artifact: the v1 `[Felix-Escalation]` Vikunja comment-write step, the historical-substrate phantom-subscription reader (which is a hacky precursor to #507's general bi-directional sync), the one-time backfill migration tool, the parity test fixtures, the parity language in agent prompts and runbooks, and the architecture data flow entry that documented the parity write. After this mission lands the escalation domain runs on JSONL alone with no historical-substrate code paths and no transitional framing anywhere.

## Technical Context

**Language/Version**: Python 3.11 (matches existing escalation domain code)
**Primary Dependencies**: stdlib only — no new imports introduced by this cleanup
**Storage**: no schema or state-file changes; existing `project-9-escalation-history.jsonl` and pre-cutover `[Felix-Escalation]` comments in Vikunja are untouched
**Testing**: pytest. Existing tests at `tests/escalation/*` and `tests/enrichment/*` are the surface
**Target Platform**: office2 (Ubuntu 24.04 LTS), `felix-admin-escalation` OpenClaw agent + `escalation-daily` cron + the `record_event` Python helper invoked from the agent's session
**Project Type**: single — scripts/ subtree of kg-automation
**Performance Goals**: nominal — each escalation event saves one Vikunja API call (PUT-comment); reconcile loses one Vikunja project-tasks GET per project (negligible)
**Constraints**: existing pre-cutover comments in Vikunja MUST be untouched; Tier 3 (Logic/Workflow) so no pre-flight checklist; agent prompts and code must land together in one merge
**Scale/Scope**: 1 active escalation project (project-9), 17 lifetime escalation events in JSONL, ≤5 events/day at steady state

## Charter Check

- **Tool registry mismatch (known, deferred)**: charter resolution reports `pytest`/`python` unavailable per the `project_charter_tool_registry_mismatch` memory. The tools are present and in active use; this is a charter-registration gap, not a real constraint. Mission proceeds.
- **Tier classification**: change-risk taxonomy Tier 3 (Logic/Workflow). No pre-flight checklist, no architecture-data updates beyond the data-flow entry removal called out in FR-011, no service-inventory edits beyond FR-012.
- **Directive 6 (deterministic vs stochastic split)**: this cleanup is entirely deterministic — code deletion + test update + doc strip. No LLM step involved.
- **Documentation standards (Directive 5)**: machine-readable updates land alongside markdown views per protocol (FR-011, FR-012).
- **Migration-completeness principle (being codified at #514)**: this mission IS the worked example of that directive. Single mission, all cleanup in one merge, no follow-ons left behind. The deletion list is enumerated up front in spec FR-001 through FR-013.

No charter violations. Charter Check passes.

## Project Structure

### Documentation (this mission)

```
kitty-specs/remove-escalation-v1-parity-01KT4VTD/
├── plan.md                            # This file
├── research.md                        # Phase 0 — Open Decisions and resolutions
├── data-model.md                      # Phase 1 — Before/after invariants
├── quickstart.md                      # Phase 1 — Local + office2 verification
├── contracts/
│   └── escalation-side-effects.contract.md
├── spec.md                            # /spec-kitty.specify output
└── tasks/                             # /spec-kitty.tasks output
```

### Source Code (repository root)

```
scripts/escalation/
├── record_completion.py               # EDIT: remove comment-write step + helpers + docstrings
├── reconcile_completions.py           # EDIT: remove phantom-subscription detector path
├── hard_fail.py                       # EDIT: remove phantom_subscription reason code + comment_count template
└── backfill_jsonl_from_comments.py    # DELETE

scripts/openclaw/agents/felix-admin-escalation/
├── AGENTS.md                          # EDIT: strip v1 parity language + phantom-subscription mentions
└── TOOLS.md                           # EDIT: strip v1 parity references

scripts/openclaw/skills/escalation/
└── SKILL.md                           # EDIT: strip v1 parity language

tests/escalation/
├── test_backfill.py                   # DELETE
├── test_record_completion.py          # EDIT: update parity-pinning assertions
├── test_reconcile_completions.py      # EDIT: drop phantom-subscription test cases
└── test_hard_fail.py                  # EDIT: drop phantom_subscription test cases

tests/enrichment/
└── test_record_completion.py          # AUDIT: drop any cross-references to escalation v1 parity

docs/runbooks/
└── escalation-ops.md                  # EDIT: strip parity-check queries + phantom-subscription guidance

docs/design/architecture/data/
├── data-flows.json                    # EDIT: remove escalation-event-write-vikunja entry; updated_by
└── service-inventory.json             # EDIT: drop v1 parity reference from felix-admin-escalation entry; updated_by

docs/design/architecture/
├── data-flows.md                      # REGEN from JSON
└── service-inventory.md               # REGEN from JSON
```

**Structure Decision**: Single Python project (kg-automation). No new modules; surgical deletions inside the existing `scripts/escalation/` package plus matching test/prompt/runbook/arch-doc updates. The deletions are wider than #512's scope but stay within a single domain (escalation) and a single mission per C-003.

## Complexity Tracking

No charter violations to justify. Section intentionally empty.

## Phase 0 Deliverable

See [research.md](research.md). Two Open Decisions were resolved during `/spec-kitty.specify`: (OD-1) which fix shape for the comment-write removal — confirmed as "delete entirely, no permanent dual-write" — and (OD-2) what to do with the phantom-subscription reader — confirmed during specify-time research as "delete, subsumed by #507."

## Phase 1 Deliverables

- [data-model.md](data-model.md) — before/after invariants table covering the five escalation event_types and the reconcile module's two sweep paths.
- [contracts/escalation-side-effects.contract.md](contracts/escalation-side-effects.contract.md) — authoritative description of the new per-state side-effect contract.
- [quickstart.md](quickstart.md) — local + office2 verification recipe.

## Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A pre-cutover task IS phantom (missed at backfill) and we lose the only detector | Very Low | Low | Detector has fired zero times in 12 days. If a phantom existed we'd have seen it. If one emerges later, operator notice or #507 catches it. |
| Test suite breakage from deletions exceeds plan | Medium | Low | Test sweep is enumerated in the plan; we run `pytest tests/escalation tests/enrichment` after each WP step. |
| `validate_docs.py` rejects the data-flow removal | Low | Low | Standard `updated_by` convention applies; this is a deletion of one entry in a known schema. |
| Reconcile's docstring edits leave dangling references to phantom logic | Medium | Low | Grep-driven NFR-002 catches stale strings. |
| The `enrichment` (habits) tests cross-reference escalation parity | Low | Low | The mission updates only assertions that explicitly reference escalation; habits-domain logic is preserved. Audit during T-step. |

## Phase Plan

- **Phase 0 (research)**: complete — both Open Decisions resolved at /specify time. See research.md.
- **Phase 1 (design)**: artifacts authored as part of /plan. See data-model.md, contracts/, quickstart.md.
- **Phase 2 (tasks)**: produced by `/spec-kitty.tasks` next. Anticipated WP shape: 2 WPs — WP01 covering the code+tests cluster (record_completion, reconcile, hard_fail, all related tests, backfill deletion); WP02 covering the prompts+runbook+arch-data cluster (SKILL.md, AGENTS.md, TOOLS.md, escalation-ops.md, data-flows.json, service-inventory.json, markdown view regen).

## Branch Strategy (reiteration)

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: true

## Next step

Run `/spec-kitty.tasks` to materialize the work packages.

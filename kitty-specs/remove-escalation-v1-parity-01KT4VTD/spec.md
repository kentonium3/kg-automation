# Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`
**Mission type**: software-dev
**Source issue**: [#376](https://github.com/kentonium3/kg-automation/issues/376)
**Target branch**: `main`
**Created**: 2026-06-02
**Governance reference**: [#514](https://github.com/kentonium3/kg-automation/issues/514) (Felix Constitution directive on migration completeness)

---

## Intent Summary

Complete the #309 escalation→JSONL migration by removing every transitional artifact still in production: the v1 `[Felix-Escalation]` Vikunja comment-write step in `scripts/escalation/record_completion.py`, the phantom-subscription detector in `scripts/escalation/reconcile_completions.py` that reads those comments as a one-off cross-system drift check (the proper general mechanism is being built at #507), all docstring and runbook references that frame the comment write as soak-window parity, the one-time `backfill_jsonl_from_comments.py` migration tool whose substrate will no longer be written, the test fixtures that pin the parity behavior, and the architecture data-flow entry that documents the parity write. After this mission lands, the escalation domain runs on JSONL alone with no dead substrates, no parity branches, no historical-substrate reader paths, and no transitional language anywhere in the code or docs.

## Background & Motivation

Mission #309 (`migrate-escalation-to-jsonl-state-model-01KS5R4D`) migrated the escalation domain from a Vikunja-comments-as-substrate model to a JSONL state log. To make rollback to v1 "a single config flip," #309 introduced a parity dual-write: every escalation event writes BOTH a JSONL record AND a `[Felix-Escalation]` Vikunja comment. The cleanup phase — remove the comment-write half — was filed as follow-on issue #376 and gated on a 3-day soak-window checklist in `docs/runbooks/escalation-soak-window.md`.

The soak-window checklist never got filled in. The dual-write ran from 2026-05-21 cutover to today (2026-06-02), 12 days past the planned soak end. On 2026-06-02, retroactive validation against the gateway cron run history and JSONL state log confirmed the migration produced zero spurious re-alerts, zero data corruption, and zero hard-fail bugs. Phase 6 was declared complete on #309 ([retroactive declaration comment](https://github.com/kentonium3/kg-automation/issues/309#issuecomment-4606129513)) and the soak runbook updated accordingly. This mission executes the cleanup that should have happened on 2026-05-25.

The drift pattern itself is being addressed at the governance layer in #514 (proposed Felix Constitution directive on migration completeness) so that future migrations cannot stall in the cleanup phase the same way.

## User Scenarios & Testing

### Primary scenario: escalation event after cleanup

1. An escalation cron tick fires (`escalation-daily` at 12:00 UTC).
2. `felix-admin-escalation` agent identifies a slipping task and invokes `record_event` with state `level_sent`.
3. The Vikunja PATCH for `done`/`rescheduled` events still happens (preserved); for `level_sent` / `snoozed` / `dismissed` events, **no Vikunja comment is written**.
4. The JSONL append still happens normally.
5. Operator inspecting the task in Vikunja sees no new `[Felix-Escalation]` comment for this event.
6. Operator inspecting the JSONL log sees the event recorded as expected.

### Secondary scenario: archived v1 comments remain

1. A Vikunja task that received `[Felix-Escalation]` comments during the pre-cleanup period still shows those historical comments in its UI.
2. No new comments accumulate for new events.

This is intentional — the comments are a historical record, not a live substrate. The issue body explicitly bounds scope to *not* delete the existing comments.

### Edge cases

- **Operator wants to re-derive JSONL from comments**: cannot. The backfill tool (`backfill_jsonl_from_comments.py`) is being deleted along with the comment-write path; once the write path is gone, the substrate to backfill from would be stale anyway. JSONL is canonical going forward. If a forensic need arises later, the git history preserves the deleted backfill script.
- **The phantom-subscription detector in `scripts/escalation/reconcile_completions.py`**: revised understanding from specify-time research on 2026-06-02. The reconcile module DOES read `[Felix-Escalation]` comments at runtime via `_COMMENT_MARKER` and `_count_escalation_comments`, walking project tasks to find tasks-with-comments-but-no-JSONL and routing them through Q10 hard-fail as `phantom_subscription`. This is a one-off, substrate-specific cross-system drift check that #507 (Felix-Vikunja bi-directional sync foundation) will subsume with a proper general mechanism. In 12 days of post-cutover operation the detector has fired ZERO times (no `phantom_subscription` hard-fail issues filed, no markers in JSONL or `/tmp/openclaw/*.log` on office2), confirming the backfill at #309 cutover was complete and the catchable set is empty. The detector reads frozen historical comments and adds no value going forward. Per the no-vestiges principle and the upcoming #507 refactor, the reader is removed in this mission.
- **Test fixtures asserting comment write**: tests that pin the parity behavior must be updated or deleted along with the production code change.

## Requirements

### Functional

| ID | Status | Requirement |
|---|---|---|
| FR-001 | proposed | The Vikunja comment-write step in `_vikunja_side_effects` (`scripts/escalation/record_completion.py`) MUST be removed. No `PUT /tasks/{id}/comments` call may originate from any escalation event path. |
| FR-002 | proposed | The `_format_v1_comment` helper and its `_COMMENT_PREFIX` constant MUST be deleted from `record_completion.py`. The module-level docstring and per-state docstrings MUST be updated to remove all references to "v1 comment", "C-001 parity", "soak", and the comment-write step in the side-effect table. |
| FR-003 | proposed | The Vikunja PATCH calls for `state="done"` (`{"done": true}`) and `state="rescheduled"` (`{"due_date": …}`) MUST be preserved. These are Vikunja state mutations, not v1-comment behavior. |
| FR-004 | proposed | The JSONL append step (Step 2) MUST be preserved as the sole canonical substrate. |
| FR-005 | proposed | The one-time migration script `scripts/escalation/backfill_jsonl_from_comments.py` MUST be deleted. Its test file `tests/escalation/test_backfill.py` MUST also be deleted. |
| FR-006 | proposed | The phantom-subscription detector in `scripts/escalation/reconcile_completions.py` MUST be deleted. Concretely: remove the `_COMMENT_MARKER` constant, the `_count_escalation_comments` helper, the phantom-subscription detection walk (the `if jsonl_path.exists():` block that enumerates project tasks and checks comment_count), and any docstring/code-comment references to the phantom detection feature within this module. The subscribed-sweep path (which checks JSONL records for tasks Felix knows about) is preserved unchanged. |
| FR-007 | proposed | The `phantom_subscription` reason code and its bug-body templating in `scripts/escalation/hard_fail.py` MUST be removed if and only if no other path produces it. Per FR-006, after the reconcile reader is deleted no producer remains. Any docstring or template that mentions `[Felix-Escalation]` comment_count as part of a hard-fail body MUST be deleted along with the producer. |
| FR-008 | proposed | All tests under `tests/escalation/` and `tests/enrichment/` that pin the v1 comment-write behavior OR the phantom-subscription detection MUST be updated to assert the new behavior (no comment write, no phantom detector) or removed if their sole purpose was to assert these features. New tests MUST cover: (a) `level_sent`/`snoozed`/`dismissed` events do NOT produce a `comment_PUT` action; (b) `done`/`rescheduled` events still produce their respective task PATCH action; (c) JSONL append still happens for all event types; (d) reconcile's subscribed-sweep continues to function with the phantom path removed. |
| FR-009 | proposed | The agent prompt artifacts in `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`, `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`, and `scripts/openclaw/skills/escalation/SKILL.md` MUST have all v1 parity language stripped. "JSONL is canonical" framing stays; "during the soak we also write the comment" framing goes; any mention of phantom-subscription detection via comments is removed. |
| FR-010 | proposed | The runbook `docs/runbooks/escalation-ops.md` MUST have its "check comments match JSONL" parity verification queries removed AND any phantom-subscription operator-runbook content removed. JSONL-only verification queries remain. |
| FR-011 | proposed | `docs/design/architecture/data/data-flows.json` MUST have the `escalation-event-write-vikunja` flow entry removed and `updated_by` set to this mission. Markdown view `data-flows.view.md` MUST be regenerated to match. |
| FR-012 | proposed | `docs/design/architecture/data/service-inventory.json` MUST have the `felix-admin-escalation` entry's purpose description updated to drop any v1-parity reference, with `updated_by` set to this mission. Markdown view regenerated to match. |
| FR-013 | proposed | After merge, a manual escalation cron tick on office2 MUST be observed to produce exactly one JSONL append and zero new `[Felix-Escalation]` comments in the targeted Vikunja task. Reconcile MUST run without exception against the post-cleanup code. |

### Non-Functional

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | proposed | The change MUST preserve the three-write contract's ordering semantics for the steps that remain (Vikunja PATCH for done/rescheduled FIRST, JSONL append SECOND). The contract becomes a "two-write" or "one-write" depending on state, but ordering between Vikunja-side-effect and JSONL append is unchanged. |
| NFR-002 | proposed | After the cleanup, `grep -rn "Felix-Escalation\|_format_v1_comment\|_COMMENT_PREFIX\|_COMMENT_MARKER\|_count_escalation_comments\|phantom_subscription\|C-001 parity\|comment.*parity" scripts/ docs/runbooks/ docs/design/architecture/data/ tests/escalation/ tests/enrichment/` MUST return zero matches in active surfaces. (Historical design documents — ADR-0002, the d6 survey, vikunja-task-model research — and this mission's own kitty-specs/ tree are permitted to reference these terms.) |
| NFR-003 | proposed | Existing tests outside the affected files MUST continue to pass without modification. |
| NFR-004 | proposed | No changes to the JSONL state log file format, schema, or location. No data migration. No state-file edits. |
| NFR-005 | proposed | The reconcile module's subscribed-sweep path (the primary cross-system drift detector that walks JSONL records and checks Vikunja state for tasks Felix knows about) MUST be preserved unchanged. Only the phantom-subscription side path (which read Vikunja comments to find tasks-Felix-doesn't-know-about) is removed. |

### Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | proposed | Existing `[Felix-Escalation]` comments on Vikunja tasks MUST be left in place as historical record. No code path may delete them. |
| C-002 | proposed | The change is Tier 3 (Logic/Workflow) under the project change-risk taxonomy. No pre-flight checklist required for the code change itself. The post-merge office2 cutover is observational verification, not a state mutation. |
| C-003 | proposed | The change MUST land in a single mission with all FRs satisfied. Per the migration-completeness principle being codified at #514, splitting cleanup across multiple missions would defeat the point of this mission's existence. |
| C-004 | proposed | The mission MUST update `docs/runbooks/escalation-ops.md` and the agent prompt artifacts BEFORE the runtime change ships, so the deployed agent never reads parity-framed instructions that don't match the code's behavior. (In practice this means the agent-prompt-file edits and the code edits land in the same merge — they're not deployment-ordered against each other, just internally consistent.) |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | No active code references the v1 comment substrate (write or read). | `grep -rn '_format_v1_comment\|_COMMENT_PREFIX\|_COMMENT_MARKER\|_count_escalation_comments' scripts/ tests/` returns zero matches; `grep -rn 'Felix-Escalation\|phantom_subscription' scripts/ docs/runbooks/ docs/design/architecture/data/ tests/` returns zero matches in active surfaces. |
| SC-002 | One manual `record_event` invocation with `state="level_sent"` produces only a JSONL append, no Vikunja write. | Verified via test (unit) and via office2 cutover observation (integration). |
| SC-003 | One manual `record_event` invocation with `state="done"` produces a task PATCH followed by a JSONL append, no comment write. | Verified via test and observation. |
| SC-004 | `scripts/escalation/backfill_jsonl_from_comments.py` and `tests/escalation/test_backfill.py` are deleted from main. | `git log --all --diff-filter=D --name-only` shows the deletion. |
| SC-005 | Phantom-subscription detection is removed from `reconcile_completions.py` and `hard_fail.py`. | Reconcile runs end-to-end against the existing JSONL state on a dry-run with no exception; `grep -n phantom_subscription scripts/escalation/` returns zero matches. |
| SC-006 | `docs/design/architecture/data/data-flows.json` does not contain `escalation-event-write-vikunja` and `validate_docs.py` passes. | `jq '[.flows[] \| select(.flow_id == "escalation-event-write-vikunja")] \| length' data-flows.json` returns 0; `python tooling/scripts/validate_docs.py` exits 0. |
| SC-007 | The deployed `SKILL.md`, `AGENTS.md`, and `TOOLS.md` on office2 no longer reference v1 parity behavior. | Post-cutover grep on office2 returns zero matches for the parity language. |
| SC-008 | Post-merge office2 cutover: one full escalation-daily cron cycle observed to deliver an escalation message to WhatsApp AND record the JSONL event AND not write a new `[Felix-Escalation]` comment to the target task; reconcile completes without exception. | Manual operator verification window after cutover (or the next natural 12:00 UTC tick). |

## Out of Scope

- Deleting existing `[Felix-Escalation]` comments from Vikunja tasks (historical record per C-001).
- Touching the habits-domain parity period (separate; tracked in `scripts/habits/*` — different cleanup).
- Changing the v2 helpers' API surfaces (`record_event`, `idempotent_record_event`) — only the side-effect path inside them changes.
- Phase 7 / tasker-enrichment work (separate cluster).
- The Felix Constitution directive itself (#514 — separate mission).

## Assumptions

- The phantom-subscription detector has fired zero times in the 12 days since #309 cutover. Verified on 2026-06-02 by `gh issue list --search "phantom_subscription"` (no hard-fail bugs filed) and by `ssh office2-claude 'grep phantom_subscription /data/services/openclaw/state/escalation/*.jsonl /tmp/openclaw/*.log'` (no runtime occurrences). The backfill at cutover was complete and the catchable set is empty.
- The proper general mechanism for Felix↔Vikunja state drift detection is being built at #507. Removing the substrate-specific phantom detector now is correct because (a) it has no remaining catchable set, and (b) #507 will subsume it generally.
- The existing test suite at `tests/escalation/` and `tests/enrichment/` is the right surface to extend with the new "no comment write, no phantom detector" assertions.
- The architecture-data JSON files (`data-flows.json`, `service-inventory.json`) accept the standard `updated_by: "#<issue>"` convention for the audit trail.

## Dependencies

- #309 (parent migration) — declared complete via [retroactive Phase 6 comment](https://github.com/kentonium3/kg-automation/issues/309#issuecomment-4606129513).
- #376 (this mission's source issue) — flipped to `spec: ready` 2026-06-02.
- #514 (governance follow-up on migration completeness directive) — independent; not blocking, but contextually adjacent.

## Key Entities

- **`_vikunja_side_effects(record, …)`**: the per-state side-effect dispatcher in `record_completion.py` (line 493 as of 2026-06-02). Currently writes a task PATCH (when applicable) then a comment PUT (always). Becoming: task PATCH (when applicable) only.
- **`_format_v1_comment`**: helper formatting the `[Felix-Escalation] YYYY-MM-DD | …` comment body. To be deleted entirely.
- **`_COMMENT_MARKER` and `_count_escalation_comments`**: the v1-comment reader entry points in `reconcile_completions.py`. The detection feature they power (phantom-subscription) is deleted along with them; the broader reconcile module remains, with only its subscribed-sweep path operational.
- **`backfill_jsonl_from_comments.py`**: one-time migration tool. To be deleted entirely.
- **`phantom_subscription` reason code** in `hard_fail.py`: the bug-body templating that uses `[Felix-Escalation]` comment_count. Deleted along with the producer in reconcile.
- **The five escalation event_types**: `level_sent`, `snoozed`, `dismissed`, `done`, `rescheduled`. Three of these (`level_sent`, `snoozed`, `dismissed`) currently produce only a comment write — after cleanup they produce no Vikunja write at all, only a JSONL append.

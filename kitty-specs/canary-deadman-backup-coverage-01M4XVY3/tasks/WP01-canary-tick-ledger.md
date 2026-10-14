---
work_package_id: WP01
title: The canary's tick declaration becomes affirmative (key ledger)
dependencies: []
requirement_refs:
- FR-011
- FR-003
- FR-010
planning_base_branch: fix/canary-deadman-backup-coverage
merge_target_branch: fix/canary-deadman-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on fix/canary-deadman-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/canary-deadman-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-canary-deadman-backup-coverage-01M4XVY3
base_commit: 0f7009f6a384fbaeded6c183df657abb84b2e1aa
created_at: '2026-10-14T19:11:25.573701+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
history:
- at: '2026-10-14T19:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan IC-05, research R11; Codex post-plan finding 1)
agent_profile: python-pedro
authoritative_surface: tests/canary/
create_intent:
- tests/canary/test_tick_ledger_reconciliation.py
- tests/canary/test_tick_ledger_verdicts.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- docs/design/architecture/data/service-inventory.json
- tests/canary/test_tick_ledger_reconciliation.py
- tests/canary/test_tick_ledger_verdicts.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – The canary's tick declaration becomes affirmative (key ledger)

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete.
- **Report progress**: `spec-kitty agent tasks add-history WP01 --note "..."`.

---

## Objectives & Success Criteria

`felix-canary`'s `health_check` in `docs/design/architecture/data/service-inventory.json` gains a `key_ledger`. The canary's tick is then judged **affirmatively**: an explicit `success` status, a fresh `completed_at_utc` with no fallback, and at least one evaluated component.

Done when:
- These four shapes, all `healthy` today (reproduced 2026-10-14), evaluate non-healthy through `scripts.canary.health.evaluate` on the real inventory target:
  1. `status` missing;
  2. `status: "partial"` (and `"error"`);
  3. `completed_at_utc: "garbage"` with a fresh `timestamp_utc`;
  4. `components_evaluated: 0`.
- The real 2026-10-14 tick document (captured verbatim, below) stays `healthy`.
- The ledger passes `tooling/scripts/validate_architecture_data.py` and has a real reconciliation harness that **executes the producer** (`scripts.canary.run.run_pass`).
- Every existing test is green: `tests/canary/`, `tests/office2/restic_backup/`, `tests/tooling/`, the `scripts/canary` tests, and the full repo suite.
- The inventory prose for `felix-health-check` and `felix-canary` describes the mission's design (T004). This WP is the single owner of `service-inventory.json` for the whole mission.

## Context & Constraints

- Spec FR-011, FR-003, FR-010. Plan IC-05. Research R11 and the "Post-plan review dispositions" table (Codex-1, Codex-7, re-review 7).
- Ledger contract: `kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`. Read § Structural rules (1–8), § Obligation 1, and § Obligation 2 in full. This WP is the contract's "Reuse by a second producer" path: declare a ledger and register a harness; **no edits to `scripts/canary/ledger.py`, `probes.py` or `tests/canary/ledger_reconcile.py`**. If you find you need one, stop: the contract says that is the contract failing.
- Producer: `scripts/canary/run.py` `run_pass` (≈ line 201). Its persisted tick (≈ lines 462–483) has exactly these keys: `status`, `completed_at_utc`, `components_evaluated`, `emitted`, `suppressed_dedup`, `coverage_gaps`, `suppressed_status`, `errors`, `duration_ms`. `component_lines` is excluded from the file. `status = "success" if not errors else "error"` (line 462), so `status` subsumes the legacy truthy-`errors` rule.
- Fixtures must mirror real inputs (charter Testing Standards). The real tick of 2026-10-14 is:

```json
{"completed_at_utc": "2026-10-14T18:44:16.390963+00:00", "components_evaluated": 32, "coverage_gaps": 0, "duration_ms": 4966, "emitted": 0, "errors": [], "status": "success", "suppressed_dedup": 1, "suppressed_status": 4}
```

## Branch Strategy

- **Strategy**: populated by finalize-tasks.
- **Planning base branch**: `fix/canary-deadman-backup-coverage`
- **Merge target branch**: `fix/canary-deadman-backup-coverage`

> Execution worktrees are allocated per computed lane from `lanes.json`.

## Subtasks & Detailed Guidance

### Subtask T001 – Declare the `felix-canary` `key_ledger`

- **Purpose**: make the canary's liveness rule affirmative (Codex-1).
- **Steps**: in the `felix-canary` entry's `health_check` (method `tick-signal-file`, `state_path` `/data/services/felix-canary/state/last-tick.json`, `max_age_seconds` 2100; leave all of these unchanged), add:

```json
"key_ledger": {
  "reconciliation_harness": "tests/canary/test_tick_ledger_reconciliation.py",
  "adjudicated": {
    "status": {"good_values": ["success"]},
    "completed_at_utc": {"freshness": true, "anchor": true},
    "components_evaluated": {"minimum": 1}
  },
  "diagnostic_only": {
    "errors": {"reason": "Summarised by status: the producer writes status \"error\" exactly when errors is non-empty (scripts/canary/run.py), so adjudicating status covers it."},
    "emitted": {"reason": "Alert volume for the pass; carries no liveness meaning."},
    "suppressed_dedup": {"reason": "Dedup bookkeeping; no liveness meaning."},
    "suppressed_status": {"reason": "Count of not-alert-eligible components skipped; no liveness meaning."},
    "coverage_gaps": {"reason": "The canary pages coverage gaps itself, per component; the tick count is diagnostic."},
    "duration_ms": {"reason": "Performance trend data."}
  }
}
```

- Keep the `expected` prose consistent with the ledger (T004).
- **Files**: `docs/design/architecture/data/service-inventory.json`.
- **Notes**: JSON formatting must match the file's existing style (indent 2; preserve key order elsewhere). Do not reformat the whole file. Verify with `git diff --stat` that only the intended entries changed.

### Subtask T002 – Tick-signal reconciliation harness

- **Purpose**: contract Obligation 2. The ledger and its emitted key set must agree, determined by **executing the producer**, never by a hand-written key list.
- **Steps**: create `tests/canary/test_tick_ledger_reconciliation.py`:
  1. Load the real inventory and `load_ledgers` (from `tests.canary.ledger_reconcile`).
  2. Drive `scripts.canary.run.run_pass(now=…, inventory=<a small fixture inventory with one healthy component>, dedup_path=tmp, tick_path=tmp/last-tick.json, ledger_dir=tmp, emit_fn=<collector>, http_get/run_cmd/read_state=<stubs>, dry_run=False)`.
  3. Read the written tick file *as text*, build an `EmissionResult` (`process_ok` = the returned summary has no runner exception; `document_text` = file text or `None`; `document` = decoded or `None`), and `assert_reconciles(emitted, REAL_LEDGERS["felix-canary"], "felix-canary")`.
  4. Add `test_felix_canary_declares_a_ledger` (contract Obligation 2.5 pin), and `test_felix_canary_harness_is_this_file` (the declaration points back here, mirroring `tests/office2/restic_backup/test_ledger_reconciliation.py:197`).
  5. Add an error-path case: drive `run_pass` so it records an error (for example, an unwritable dedup path, which `run_pass` catches into `errors`). Assert the written tick has `status == "error"`, and that the **key set** is identical. This is reconciliation's key-set property, plus a check that the `errors` → `status` subsumption in T001 holds on a real producer run.
- **Notes**: the existing restic harness's `test_selection_matches_the_full_ledger_declaring_set` and `test_declared_harness_paths_exist_on_disk` derive from the real inventory, so they discover the new ledger automatically. They pass only if this file exists, which is why T001 and T002 land together.

### Subtask T003 – Evaluator verdict tests

- **Purpose**: prove FR-011's non-vacuity. Each shape is healthy before T001 and non-healthy after; the positive control uses the same fixture.
- **Steps**: create `tests/canary/test_tick_ledger_verdicts.py`, which goes through `scripts.canary.registry.load_targets(load_inventory(<repo-root>/…))` (note that it **returns `(targets, gaps)`**) and `scripts.canary.health.evaluate(target, now, http_get=_refuse, run_cmd=_refuse, read_state=lambda p: doc)`. Parametrize:

| case | doc (from the real tick) | expected outcome |
|---|---|---|
| real tick, `now` 5 min after `completed_at_utc` | as captured | `healthy` (positive control) |
| status missing | pop `status` | not `healthy` |
| status partial / error / null | replace | not `healthy` |
| broken anchor + fresh fallback | `completed_at_utc: "garbage"`, add fresh `timestamp_utc` | not `healthy`; evidence names `completed_at_utc` |
| zero components | `components_evaluated: 0` | not `healthy` |
| stale | `now` = `completed_at_utc` + 17 days | `stale` |
| future-dated | `completed_at_utc` = `now` + 1 h | `stale` (future skew) |

- Use the **real** inventory. Do not use a test copy of the declaration: the point is that the shipped declaration is affirmative.
- **Parallel?**: yes, after T001.

### Subtask T004 – Inventory prose (single owner of the file)

- **Purpose**: FR-010 and Codex-7 (+ re-review 7). The inventory is authoritative, so it must describe the mutual watch and stop naming the retired path as live.
- **Steps**:
  - `felix-health-check` entry:
    - Update `purpose`, `expected`/`note` prose, and any dependency field that names `/home/claude/helper-scripts/health-check.sh` (≈ lines 2430–2440): the script now lives at `scripts/office2/felix_health_check/health-check.sh` and runs from the checkout.
    - Add to the prose: the health check evaluates `felix-canary` (dead-man's switch) and `restic-backup` via the canary's own evaluator, with `coverage_checks`, `script_status` and `script_path` in `last-run.json`; and the mutual watch with the canary (#891 direction).
    - **Do not change** `method`, `endpoint`, `max_age_seconds` or `success_status_values` (the canary reads them).
  - `felix-canary` entry `note`: add one sentence noting the ledger (#1063) and that it also tightens the canary's self-probe.
  - Bump the file-level `last_updated` / `updated_by` if the file carries them (follow existing convention).

### Subtask T005 – Validators and suites

- **Steps** (from the repo root of the lane worktree):

```bash
python3 tooling/scripts/validate_architecture_data.py
python3 tooling/scripts/validate_docs.py
python3 -m pytest tests/canary tests/office2/restic_backup tests/tooling scripts/canary -q
python3 -m pytest -q -x
```

- All must pass. If any pre-existing canary test asserted the legacy healthy reading of a non-success tick for `felix-canary`, update it to the new affirmative verdict, citing FR-011 in the test. If such a test lives outside `tests/canary/`, record the out-of-map edit with a one-line rationale in `add-history`.

## Test Strategy

pytest, offline. The new files are listed in `create_intent`. Required: T003's table (each row a test id), T002's reconciliation + error-path + pins.

## Risks & Mitigations

- **Live behavior change**: the canary's self-probe becomes stricter. A real `error` tick already read `failed` (legacy truthy-`errors`), so this is the same outcome through the ledger. A tick missing `status` now fails, which is the intent.
- **Partial landing**: ledger without harness fails the restic suite's harness-path test. Commit T001 and T002 together.

## Review Guidance

- Confirm that no file under `scripts/canary/` or `tests/canary/ledger_reconcile.py` changed.
- Confirm the harness executes `run_pass` (not a key list) and that both the reconciliation and the error-path test would fail if a key were added to the producer without a declaration. Try it: temporarily add a key and watch it go red.
- Confirm T003 uses the real inventory, and that the positive control shares the fixture.
- Confirm the `felix-health-check` `health_check` fields the canary reads are byte-identical (`git diff`).

## Progress & Status

- `spec-kitty agent tasks add-history WP01 --note "<what you did>"`
- `spec-kitty agent tasks move-task WP01 --to <status>`
- Implement with: `spec-kitty agent action implement WP01 --agent claude --mission canary-deadman-backup-coverage-01M4XVY3`

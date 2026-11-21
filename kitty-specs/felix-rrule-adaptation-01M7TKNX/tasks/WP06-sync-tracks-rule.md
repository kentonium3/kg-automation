---
work_package_id: WP06
title: Sync sees the rule
dependencies:
- WP01
requirement_refs:
- FR-016
- NFR-004
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 22c2c4c25d38efe9e3f55c23174a947824141ffa
created_at: '2026-11-19T22:24:40.879090+00:00'
subtasks:
- T026
- T027
- T028
- T029
phase: Phase 2 - Detection
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/sync/
create_intent: []
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/sync/diff.py
- scripts/sync/classify.py
- scripts/sync/cycle.py
- scripts/sync/state.py
- tests/common/conftest.py
- tests/common/test_sync_cache.py
- tests/sync/test_diff.py
- tests/sync/test_classify.py
- tests/sync/test_cycle.py
- tests/sync/test_state.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP06 – Sync sees the rule

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

Audit row 22 (#1111). The sync's task cache never held `repeat`, so a stripped rule could never show up as a divergence.

After this WP:
- `TRACKED_TASK_FIELDS` (`scripts/sync/diff.py:40-48`) replaces `repeat_after`/`repeat_mode` with `repeat` and `repeats_from_current_date`.
- `repeat` is compared in WP01's normal form (a new entry beside `_DATETIME_FIELDS` and `_LIST_FIELDS` at L118-119).
- `classify.DOWNSTREAM_AFFECTING_FIELDS` (L38-45) gets the same replacement, so a rule change is `unsafe_to_auto_resolve`.
- **Seed-on-missing-key.** A cached entry that lacks a tracked key adopts the live value **without** a divergence, once. Each seed is written to `seed-ledger.jsonl` in the sync state directory, and the cycle summary reports `baseline_seeded=N`.
- **No `SCHEMA_VERSION` bump.** `state.py:32`; a bump forces an operator re-bootstrap.

Done when:
- A first cycle over a pre-upgrade cache produces 0 divergences and N seeds.
- A second cycle with one rule removed produces exactly 1 divergence classified unsafe (`uc3_downstream_behavior`).
- NFR-004 holds in tests.

## Context & Constraints

- Spec: FR-016, NFR-004. Plan IC-06. research.md R-008. data-model.md, sync cache entry section. post-plan-review.md finding 9.
- Current mechanics (verified):
  - `compute_divergences` (`diff.py:175+`) compares `task.get(f)` with `cached_fields.get(f)`.
  - `_canonicalize` is at L155-161.
  - `cycle.py:_apply_cache_updates` (L614+, the write at L656-658) stores `{f: task.get(f) for f in TRACKED_TASK_FIELDS}`.
  - The cache lives at `STATE_DIR_DEFAULT=/data/services/openclaw/state/sync` (`state.py:35`), overridable with `FELIX_SYNC_STATE_DIR`.
  - The guard path and the G-3 daily cap are in `emit.py`; don't change them.
- `tests/common/conftest.py:81-83` carries a **copy** of `_TRACKED_TASK_FIELDS`, and `mock_sync_cache_fixture` (L87, seeds at L108-109) uses `repeat_after`/`repeat_mode`. Convert both. This WP owns `tests/common/conftest.py`; keep `mock_vikunja_urlopen` untouched, because other WPs depend on it.
- Check what the sync fetches. It uses list endpoints, and list bodies carry `repeat` but **not** `repeats_rrule` (research.md R-003). So track `repeat`, never `repeats_rrule`.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP06 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T026 – Track the rule with a normaliser

- **Steps**:
  1. `diff.py`: `TRACKED_TASK_FIELDS = (title, done, due_date, project_id, repeat, repeats_from_current_date, labels)`. Keep the order stable.
  2. Add `_RULE_FIELDS = {"repeat"}`. `_canonicalize` returns `vikunja_rule.normalise(value)` for it.
  3. `repeats_from_current_date`: canonicalise to `bool(value)`, so `None` and `False` are equal.
  4. Grep `scripts/sync/**` for other `repeat_after` uses (`cleanup.py:101` is a docstring owned by WP07; leave it) and for any code that assumes tracked values are scalars.

### Subtask T027 – Seed on a missing key, with a ledger

- **Steps**:
  1. In `compute_divergences`, for each tracked field `f`: when `f not in cached_fields`, which means the key is **absent** rather than None, do not emit a divergence. Add `(task_id, f, canonical live value)` to a `seeds` list returned alongside the divergences. Pick a small dataclass or tuple return, and update the callers.
  2. In `cycle.py`, after the cycle's cache write, which already stores the live subset and so persists the seed:
     - append one JSON line per seed to `seed-ledger.jsonl` (`{"cycle_id", "task_id", "field", "seeded_value", "at"}`), in the same state directory, atomically with fsync, following the existing state-file patterns in `state.py`;
     - add `baseline_seeded` to the cycle summary and log line.
  3. **Bootstrap path** (`run_bootstrap`, `cycle.py:431-580`): a fresh bootstrap rebuilds the cache with all fields, so there are no seeds. Confirm it, and add a test.
  4. Idempotency: a second cycle finds the key present, so it produces no seed. The seed happens exactly once per task per field.

### Subtask T028 – Downstream-affecting classification

- **Steps**:
  1. `classify.DOWNSTREAM_AFFECTING_FIELDS`: replace `repeat_after` and `repeat_mode` with `repeat` and `repeats_from_current_date`.
  2. Confirm that a `repeat` divergence follows the existing unsafe path (L138-168) and is reported with both normalised values.

### Subtask T029 – Tests

- `tests/sync/test_diff.py`:
  - normaliser equality (casing, list order, `read_only`);
  - a missing key gives a seed and no divergence;
  - a present-but-different key gives a divergence;
  - `None` vs `False` for the flag gives no divergence.
- `tests/sync/test_cycle.py`:
  - **First cycle** over an old-shape cache (keys absent): 0 divergences, N seeds, ledger lines written, `baseline_seeded=N`.
  - **Second cycle** with one task's `repeat` set to None: exactly 1 divergence, classified unsafe.
  - **Post-seed loss** (finding 9): a task first observed with no rule seeds `None`. Assert the ledger records `seeded_value: null`. That is the evidence WP10's inventory cross-checks.
- `tests/sync/test_classify.py`: the rule divergence is unsafe.
- `tests/common/conftest.py` + `tests/common/test_sync_cache.py`: convert the copies and fixtures to the new shape.

```bash
python3 -m pytest -q tests/sync tests/common
```

```bash
make test
```

## Risks & Mitigations

- **A conflict storm** if seeding is wrong. The first-cycle test is the guard; it must assert 0 divergences across many tasks.
- **Ledger growth.** One line per task per field, once, so the ledger stays small. Skip rotation.

## Review Guidance

- Is the seed only on an *absent* key, never on a None value?
- Is the ledger written for every seed, including `null` seeds?
- Is `SCHEMA_VERSION` unchanged?

## Progress & Status

Use `spec-kitty agent tasks add-history WP06 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.

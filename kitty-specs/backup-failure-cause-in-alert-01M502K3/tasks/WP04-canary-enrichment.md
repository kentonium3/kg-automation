---
work_package_id: WP04
title: Canary and health-check alerts name the cause
dependencies:
- WP02
- WP03
requirement_refs:
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- NFR-001
- NFR-002
- NFR-004
- C-003
- SC-001
- SC-002
- SC-003
planning_base_branch: fix/backup-failure-cause-in-alert
merge_target_branch: fix/backup-failure-cause-in-alert
branch_strategy: Planning artifacts for this mission were generated on fix/backup-failure-cause-in-alert. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/backup-failure-cause-in-alert unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-backup-failure-cause-in-alert-01M502K3
base_commit: 87258a114840c7aac4ac45239ab5757821fda342
created_at: '2026-10-15T15:52:23.108921+00:00'
subtasks:
- T010
- T011
- T012
- T013
- T014
history:
- at: '2026-10-15T16:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (post-plan Codex review APPROVE)
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- tests/canary/test_probes_cause.py
- tests/office2/felix_health_check/test_coverage_cause.py
- tests/docs/test_restic_cause_codes_documented.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/probes.py
- scripts/canary/ledger.py
- tests/canary/test_probes_cause.py
- tests/office2/felix_health_check/test_coverage_cause.py
- tests/docs/test_restic_cause_codes_documented.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Canary and health-check alerts name the cause

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `fix/backup-failure-cause-in-alert` · **Merge target branch**: `fix/backup-failure-cause-in-alert`. Worktrees come from `lanes.json`.

## Context

The authoritative inputs:
- `data-model.md` § "Evidence enrichment (runtime)" (the decision table)
- the contract `contracts/key-ledger-cause-member.md` § Semantics
- `research.md` R3

The code facts:
- `scripts/canary/probes.py::_probe_freshness_with_ledger` (~line 606) is the only function with both `pointer` and `ledger` in scope. Its non-ok returns:
  - the `unhealthy` branch (~626–629)
  - the explicit-error branch on undeclared keys
  - everything returned by `_ledger_freshness_result` (non-anchor failures with `ok=False`, and `_freshness_verdict` stale results)
  - the `unknown` branch (`_unevaluable`), which is **not** enriched
- `health.evaluate` copies the evidence (`health.py:158`), and `run._build_alert` uses it as the description (`run.py:165-195`).
- felix-health-check's `coverage.py:185` calls `health.evaluate`. `felix_health_check/run.py:297` renders `f.evidence`, and details are truncated at 500 characters (`run.py:287`).
- `dedup.decide` never reads the evidence (`dedup.py:177`).

## Objective

Every non-ok, evaluable verdict from a ledger-backed pointer gains `; cause: <declared text>` when the pointer's cause key holds a known code. `ok`, `stale`, `evaluable` and `signal` never change.

## Subtasks

### T010 – Runtime reader

Add a pure, total function in `scripts/canary/ledger.py`, or as a private helper in `probes.py` if that reads more cleanly:

```python
def cause_text(pointer: Any, ledger: Any) -> str | None:
```

It returns:
- `None` when:
  - the ledger has no well-formed `cause` member. Re-check the shape locally: object, `key` a non-empty str, `codes` a non-empty dict. The runtime must not trust the validator.
  - the pointer is not a dict.
  - the value is absent, `None`, or not a `str`.
- `codes[value]` when the value is a known code **and** the declared text is a str of 1–120 characters with no control characters. Otherwise it returns `None`; a bad declared text is never emitted.
- the fixed marker `"unrecognised failure code"` for any other str value. **Never** the raw value.

It must never raise. Wrap nothing broadly; check types explicitly.

### T011 – Enrichment in `_probe_freshness_with_ledger`

- Compute `text = cause_text(pointer, ledger)` once.
- For **every** returned `ProbeResult` with `ok is False` **and** `evaluable is True`, return a copy (`dataclasses.replace`) whose evidence is `f"{evidence}; cause: {text}"` when `text` is not `None`. This includes stale results.
- Leave `ok=True` results and `unknown` results untouched.
- Implement it as one small wrapper at the function's return points, for example by renaming the body to `_probe_freshness_with_ledger_inner` and wrapping it. Do not scatter the logic across branches.
- Add a short docstring paragraph that cites #1067 and says the cause decorates and never decides.
- **No component-name branching (C-003).**

### T012 – Canary tests (`tests/canary/test_probes_cause.py`)

Use the real `restic-backup` ledger loaded from `docs/design/architecture/data/service-inventory.json`, plus synthetic ledgers.

- **Positive**: a not-mounted pointer (as WP02's script would write it: `restic_exit_code: 127`, `prune_exit_code: 127`, snapshot ts null or old, `failure_reason: "backup_mount_missing"`) is not ok, and its evidence ends with `; cause: backup drive /mnt/backups is not mounted`.
- **All four codes** produce four distinct evidence suffixes (SC-002).
- **Verdict invariance (FR-007 / SC-003)**: for each fixture, the same pointer without `failure_reason` gives identical `ok`, `stale`, `evaluable` and `signal`, and its evidence equals the enriched evidence minus the suffix.
- **Healthy plus a stray cause**: a fully healthy pointer with `failure_reason: "backup_failed"` stays ok, and its evidence is unchanged.
- **Fail-safe (FR-008)**:
  - The value is absent, `None`, `5`, `[]` or `{}`: the evidence is byte-identical to the baseline.
  - The value is `"zzz"`: the suffix is the fixed marker.
  - The value is 10 kB of text, or contains `\n`, `<script>` or ANSI escapes: none of the raw bytes appear in the evidence, and the suffix is the fixed marker.
  - The ledger's `cause` is malformed (not a dict, missing `codes`, `codes` not a dict, or text longer than 120 characters): there is no suffix and nothing raises.
- **Unknown untouched**: a pointer that makes the ledger outcome `unknown` gets no suffix.
- **Dedup and cadence (NFR-001)**: drive `scripts.canary.run`, or the smallest public entry point that does evaluate → dedup → emit, over two ticks with and without the cause. The emit decisions are identical. Use the existing `tests/canary/test_run.py` patterns and fakes.
- **NFR-002**: the suffix is at most `len("; cause: ") + 120` characters.

### T013 – Health-check (`tests/office2/felix_health_check/test_coverage_cause.py`)

Using the patterns in `tests/office2/felix_health_check/test_run.py`, show that the `restic-backup` coverage finding for the not-mounted pointer carries the cause text, and that its rendered detail line `coverage:restic-backup` contains it within the 500-character truncation. Also show that the same pointer without a cause renders exactly as before.

### T014 – Docs coverage (`tests/docs/test_restic_cause_codes_documented.py`)

- Load the `restic-backup` ledger's `cause.codes` from the inventory, and assert that every code name appears literally in `docs/runbooks/restic-backup-ops.md`.
- Assert the set is non-empty. This is the non-vacuity guard: the test must fail if `cause` is removed.
- If `tests/docs/` has no `__init__.py` and the repo's other test packages need one, add it, and record that one-line out-of-map file in the WP history.

## Definition of Done

- `.venv/bin/python3 -m pytest tests/canary tests/office2 tests/docs tests/architecture -q` passes.
- The full suite passes: `TMPDIR=/dev/shm .venv/bin/python3 -m pytest -q -p no:cacheprovider`, with 0 new failures (NFR-004).
- The validator reports 0 findings.

## Risks

- `ProbeResult` is a frozen dataclass; use `dataclasses.replace`.
- Do not enrich in `health.py` or `run.py`. That would duplicate the logic and could double-suffix.
- The canary runs every 15 minutes on office2 from the checkout. Any exception here becomes a `tick_error`, so totality is tested, not assumed.

## Reviewer guidance

- Try to break `cause_text` with odd types.
- Confirm the inner/outer wrap covers every return, including the explicit-error and stale paths. Write a quick ad hoc fixture if needed.
- Confirm no component name appears in the new code.

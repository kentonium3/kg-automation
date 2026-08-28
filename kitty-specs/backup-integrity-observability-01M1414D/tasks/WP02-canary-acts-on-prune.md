---
work_package_id: WP02
title: Canary acts on the prune outcome
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-009
planning_base_branch: feat/backup-integrity-observability
merge_target_branch: feat/backup-integrity-observability
branch_strategy: Planning artifacts for this mission were generated on feat/backup-integrity-observability. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/backup-integrity-observability unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T11:30:00Z'
subtasks:
- T005
- T006
- T007
phase: Phase 1 - Make it consequential
history:
- at: '2026-08-28T11:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/probes.py
create_intent:
- tests/canary/test_probes_prune.py
execution_mode: code_change
owned_files:
- scripts/canary/probes.py
- tests/canary/test_probes_prune.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP02 — Canary acts on the prune outcome

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/backup-integrity-observability`
- **Final merge target**: `feat/backup-integrity-observability`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch`.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

WP01 makes the prune outcome *exist*. This work package makes it *matter*. A
field the health surface does not read is worse than no field, because the
evidence then sits in the pointer beside a check still reporting healthy.

While here, close a second hole the post-plan review found in the same component.

**Maps to**: FR-003, FR-009; NFR-001, NFR-002; C-006.

---

## ⚠ Two traps, both verified against the real code

**1. The prune good-set is `{0}` — do NOT reuse `_RESTIC_OK_EXIT_CODES`.**

```python
_RESTIC_OK_EXIT_CODES: frozenset[int] = frozenset({0, 3})   # probes.py:99
```

That set is `{0, 3}` because a restic **backup** exiting 3 completed with
warnings but still produced a snapshot. For `forget --prune`, 3 carries no such
guarantee, and `restic-backup.sh` already agrees — it treats only `PRUNE_RC == 0`
as success. Reusing the backup's set would accept a prune that did not apply
retention, which is precisely the failure being fixed.

**2. Restic freshness currently falls through and reads healthy without a
snapshot.** Verified through the real probe:

```
{"restic_exit_code": 0, "snapshot_timestamp_utc": null,
 "script_finished_at_utc": <fresh>}   ->  ok=True  stale=False
```

`TIMESTAMP_KEYS` tries `completed_at_utc`, then `snapshot_timestamp_utc`, then
`script_finished_at_utc` — so a run that finished without producing a snapshot
resolves against the wrong anchor and reads fresh. The inventory's own `expected`
prose says the snapshot timestamp "must be non-null". The code and the
declaration disagree, and the code is the lenient one.

---

## Subtasks

### T005 — Check `prune_exit_code` with a `{0}` good-set

**Steps**:

1. In `_explicit_error`, beside the existing `restic_exit_code` branch, add a
   `prune_exit_code` branch with its **own** good-set of `{0}`. Define it as a
   separate module constant; do not reuse `_RESTIC_OK_EXIT_CODES`.
2. Guard with `isinstance(code, int)` exactly as the neighbouring checks do, so
   an absent key or non-integer is ignored and legacy pointers are unaffected
   (NFR-002).
3. Return an evidence string in the established shape,
   e.g. `f"prune_exit_code={code}"`.
4. Order it after the backup check: when both failed, the backup is the more
   fundamental fact and should be the reported evidence.
5. Comment why the set differs from the backup's. Without that, a future reader
   "tidies up" the duplication and reintroduces the bug.

**Validation**:
- [ ] A separate constant, not `_RESTIC_OK_EXIT_CODES`
- [ ] Absent key → no signal; non-integer → no signal

### T006 — Fail closed when a restic pointer has no snapshot timestamp

**Steps**:

1. When a pointer carries `restic_exit_code` (i.e. it is a restic backup pointer)
   **and** `snapshot_timestamp_utc` is absent, null, or unparseable, treat that
   as an explicit failure rather than falling through to another timestamp key.
2. Scope it narrowly to that condition. Components that legitimately have no
   `snapshot_timestamp_utc` and never emit `restic_exit_code` must be untouched —
   this is a shared code path and a broad change would flip unrelated components.
3. Evidence string should name the actual problem, e.g.
   `"restic pointer has no usable snapshot_timestamp_utc"`, not a generic error.

**Validation**:
- [ ] Null/absent snapshot timestamp with `restic_exit_code` present → not ok
- [ ] A non-restic pointer with no `snapshot_timestamp_utc` is unaffected

### T007 — Prove it through the real probe

**Purpose**: These assertions must run against the actual judge. A hand-rolled
mimic would not have caught either trap above.

**Steps**:

Create `tests/canary/test_probes_prune.py` using `scripts.canary.probes.run_probe`
with an injected `read_state`, covering:

| Pointer | Required verdict |
|---|---|
| `restic_exit_code 0`, `prune_exit_code 0`, fresh snapshot ts | healthy |
| `restic_exit_code 0`, `prune_exit_code 1` | **not ok** |
| `restic_exit_code 0`, `prune_exit_code 3` | **not ok** — the trap |
| `restic_exit_code 0`, `prune_exit_code 127` | **not ok** — never attempted |
| `restic_exit_code 0`, **no** `prune_exit_code` (legacy) | healthy — NFR-002 |
| `restic_exit_code 0`, `snapshot_timestamp_utc: null`, fresh `script_finished_at_utc` | **not ok** — FR-009 |
| `restic_exit_code 3`, `prune_exit_code 0` | healthy — existing backup semantics |
| a non-restic `tick-signal-file` pointer with `completed_at_utc` only | healthy — no regression |

Assert on `ProbeResult.ok` / `.stale`, and include the evidence string in the
failure message so a regression says *why*.

**Validation**:
- [ ] All eight rows pass
- [ ] `python3 -m pytest tests/canary/ -q` green (the existing suite too)

---

## Definition of Done

- [ ] Prune good-set is `{0}`, separate constant, commented
- [ ] Restic freshness fails closed with no snapshot timestamp
- [ ] All eight probe rows asserted through the real `run_probe`
- [ ] `python3 -m pytest tests/canary/ -q` green, including the inventory data guard
- [ ] `make test` at or above the 6216 floor
- [ ] No file outside `owned_files` modified

## Out of scope

- The inventory `expected` prose, which must be corrected to match — **WP05**.
- `scripts/deploy/lib/snapshot.py`. Its Tier-2 gate must stay **prune-agnostic**:
  a failed prune does not invalidate the snapshot, so it must not block deploys.
  The asymmetry is deliberate — prune failure alerts, it does not gate.

## Reviewer guidance

The single highest-value check: confirm `prune_exit_code: 3` is asserted
**unhealthy**. That is the case a careless implementation gets wrong by reusing
the backup's `{0, 3}` set, and it is invisible unless tested. Then confirm the
legacy row (no prune key) still passes — a change that breaks every historical
pointer would be a worse regression than the bug. Finally check T006 is scoped to
restic pointers only; `probes.py` is shared by every component.

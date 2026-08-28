---
work_package_id: WP04
title: Drift-check freshness pointer
dependencies:
- WP01
requirement_refs:
- FR-006
planning_base_branch: feat/crontab-backup-coverage
merge_target_branch: feat/crontab-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on feat/crontab-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/crontab-backup-coverage unless the human explicitly redirects the landing branch.
created_at: '2026-08-28T00:37:21Z'
subtasks:
- T017
- T018
- T019
phase: Phase 2 - Make the drift check observable
history:
- at: '2026-08-28T00:37:21Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/enforcement/drift_check.py
create_intent:
- tests/openclaw/enforcement/test_drift_check_pointer.py
execution_mode: code_change
owned_files:
- scripts/openclaw/enforcement/drift_check.py
- tests/openclaw/enforcement/test_drift_check_pointer.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP04 — Drift-check freshness pointer

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/crontab-backup-coverage`
- **Final merge target**: `feat/crontab-backup-coverage`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch` when
  the worktree is created.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

`scripts/openclaw/enforcement/drift_check.py` runs daily at 06:00 and enforces
agent-workspace drift. It writes **no state file**. Its only trace is
`/tmp/drift-check.log`, which `systemd-tmpfiles --remove --boot` empties at every
boot. It stopped for roughly eight hours on 2026-08-27 and nothing anywhere would
ever have reported it.

Give it a durable freshness pointer so WP05 can register a health check that can
actually fail.

**Done when**: every run writes a pointer under `/data/services/openclaw/state/enforcement/`,
and the pointer distinguishes "the runner executed correctly" from "drift was
found".

**Maps to**: FR-006, NFR-004.

---

## ⚠️ The trap this work package exists to avoid

`drift_check.py` ends with:

```python
# scripts/openclaw/enforcement/drift_check.py:~304
sys.exit(1 if has_drift else 0)
```

So exit `1` means **"I ran fine and found drift"** — a successful run.

Meanwhile the canary treats any non-zero `exit_code` in a pointer as an explicit
failure that short-circuits ahead of freshness:

```python
# scripts/canary/probes.py:267-269
if "exit_code" in pointer:
    code = pointer["exit_code"]
    if isinstance(code, int) and code != 0:
        return f"exit_code={code}"
```

Writing the process exit code straight into the pointer would therefore make
every drift-finding run page as a broken component. That is the #891 defect class
inverted: instead of a check that cannot fail, a check that fires on healthy
runs — which trains the operator to ignore it, and is how a real failure gets
missed.

**The pointer's `exit_code` means "did the runner execute correctly", never "was
the result clean".**

---

## Subtasks

### T017 — Emit a durable freshness pointer

**Purpose**: Give the component something a health check can honestly read.

**Steps**:

1. Write to `/data/services/openclaw/state/enforcement/last-tick.json`. This
   follows the established `/data/services/openclaw/state/<component>/`
   convention — sibling directories already exist for `intake`, `habits`,
   `escalation`, `sync`, and others.
2. **Not** `/tmp`. Two independent gates block it:
   `tests/canary/test_inventory_health_checks.py:131-139` pins the set of
   components probing `/tmp` and fails when it changes (only
   `obsidian-sync-heartbeat` is grandfathered, owned by #894), and the same file
   restricts `max_age_seconds` to pointer methods.
3. Fields per `data-model.md` §3: `status`, `exit_code`, `completed_at_utc`,
   `has_drift`.
4. Atomic write — `tempfile.mkstemp` in the destination directory then
   `os.replace`. Create the directory if absent.
5. Emit on **both** the `check` and `report` subcommands: the pointer answers
   "did the scheduled job run", which is true in both modes.
6. A pointer-write failure must never abort the drift check. Match
   `deploy_agent_prompts.py:420` — swallow `OSError`, keep going. Losing the
   freshness signal is strictly better than crashing enforcement.
7. Make the pointer path overridable (constant or flag) so T019 can test without
   writing to a real `/data` path.

**Validation**:
- [ ] Pointer written on every invocation of both subcommands
- [ ] Directory auto-created
- [ ] A write failure does not change the process exit code

### T018 — Map exit codes to runner health

**Purpose**: The separation described above.

**Steps**:

Implement exactly this mapping:

| Process exit | Meaning | `status` | pointer `exit_code` | `has_drift` |
|---|---|---|---|---|
| `0` | ran, no drift (or remediated) | `success` | `0` | `false` |
| `1` | ran, drift found (`report`) | `success` | `0` | `true` |
| `2` | runner errored | `error` | `2` | `null` |

1. Do **not** change the process exit codes themselves — callers and the crontab
   redirect depend on them. Only the *pointer* contents are being defined here.
2. `has_drift` is diagnostic. It must not be a field the canary's explicit-error
   scan reads — do not name it `error`, `errors`, `cycle_error`, or `exit_status`,
   all of which that scan inspects.
3. Add a comment at the mapping site explaining why exit 1 is recorded as
   healthy. Without it, a future reader will "fix" this back into a bug.

**Validation**:
- [ ] Drift-found run writes `exit_code: 0`, `status: success`, `has_drift: true`
- [ ] Error run writes `exit_code: 2`, `status: error`
- [ ] Process exit codes unchanged from current behaviour

### T019 — Tests

**Steps**:

Create `tests/openclaw/enforcement/test_drift_check_pointer.py`:

1. **Drift-found is healthy** — build the pointer a drift-finding run produces,
   then assert `scripts.canary.probes.run_probe` judges it **ok**. Use the real
   `run_probe` with an injected `read_state`, not a hand-rolled mimic — the point
   is to test against the actual judge.
2. **Runner error is unhealthy** — the exit-2 pointer must not be ok.
3. **Staleness** — an old `completed_at_utc` past `max_age_seconds` reports
   `stale=True`, proving the check can fail at all.
4. **Clean run** — `has_drift: false`, healthy.
5. **Pointer-write failure is non-fatal** — patch the write to raise `OSError`;
   assert the drift check still completes with its normal exit code.

Use `tmp_path` throughout.

**Validation**:
- [ ] `python3 -m pytest tests/openclaw/enforcement/test_drift_check_pointer.py -v` passes
- [ ] Test 1 uses the real `run_probe`

---

## Definition of Done

- [ ] Pointer written on every run, atomically, outside `/tmp`
- [ ] Exit mapping implemented with the explanatory comment
- [ ] Tests green, including drift-found-is-healthy via the real probe
- [ ] `make test` at or above the 6177 floor
- [ ] The crontab entry is **unchanged** — verify `crontab -l` on office2 is untouched
- [ ] No file outside `owned_files` modified

## Out of scope

- Registering the component in `service-inventory.json` — **WP05**. This WP only
  creates the signal WP05 will point at.
- Moving `/tmp/drift-check.log` or changing the crontab redirect. That is #894's
  territory; touching the crontab here would drift `crontabs.txt` during the
  window in which it is still the only copy of the crontab (C-005).
- Changing what counts as drift, or the remediation behaviour.

## Reviewer guidance

The whole WP is one idea: liveness is not the same as result. Verify the exit
mapping table is implemented literally, and that test 1 exercises the genuine
`run_probe` rather than asserting on a dict the test itself constructed and
judged. Confirm nothing under `/tmp` is written, and that `crontab -l` on office2
is unchanged.

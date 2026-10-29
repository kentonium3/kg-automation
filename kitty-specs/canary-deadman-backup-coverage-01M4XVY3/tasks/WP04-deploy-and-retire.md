---
work_package_id: WP04
title: Deploy, retire the host copy, live proof
dependencies:
- WP03
requirement_refs:
- FR-008
- FR-009
- C-004
- SC-002
- SC-005
planning_base_branch: fix/canary-deadman-backup-coverage
merge_target_branch: fix/canary-deadman-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on fix/canary-deadman-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/canary-deadman-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-canary-deadman-backup-coverage-01M4XVY3
base_commit: 0f7009f6a384fbaeded6c183df657abb84b2e1aa
created_at: '2026-10-14T19:42:21.060537+00:00'
subtasks:
- T016
- T017
- T018
- T019
phase: Phase 3 - Deploy
history:
- at: '2026-10-14T19:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan IC-03; Codex-2/7, re-review 2/7; paula-7)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/
create_intent:
- scripts/deploy/deploy-health-check-coverage.py
- tests/deploy/test_deploy_health_check_coverage.py
- deploys/queued/health-check-coverage.yaml
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/deploy/deploy-health-check-coverage.py
- tests/deploy/test_deploy_health_check_coverage.py
- deploys/queued/health-check-coverage.yaml
- scripts/office2/deploy/felix-health-check.sh
- scripts/deploy/deploy-deterministic-monitoring-checks.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Deploy, retire the host copy, live proof

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history WP04 --note "..."`.

---

## Objectives & Success Criteria

A queued manifest and its entrypoint. On office2, after the merge to `main`, felix-deployer runs the entrypoint with `--apply`. The apply:
1. runs the health check once, for real;
2. proves from the **fresh** run record that the new coverage is live and complete;
3. only then moves `~/helper-scripts/health-check.sh` to a dated retired file.

A re-apply is a no-op success.

Done when the entrypoint tests pass, the manifest validates (deploy-pipeline tests in `tests/deploy/` and any manifest-schema test), and the pre-merge `--dry-run` has run against live office2 state via `git archive` (quickstart.md). Record its output in `add-history`.

## Context & Constraints

- Spec FR-008, FR-009, C-004, SC-002, SC-005. Plan IC-03. Research R8 and the review dispositions (Codex-2, Codex-7, re-review 2/7, paula-7).
- Patterns to copy: `scripts/deploy/deploy-monotonic-timer-units.py` (#1062; preflight user/home, `_emit` JSON lines, injected runner/sleep, `--dry-run`/`--apply`) and its tests `tests/deploy/test_deploy_monotonic_timer_units.py`; manifest `deploys/applied/0031-monotonic-timer-units.yaml`; `docs/runbooks/deploy/discipline.md`.
- ⚠ The entrypoint runs **on office2**; never wrap commands in `ssh office2-claude`. office2 has **no pytest**, so there is no pytest pre-check in the manifest. Manifest `notes` must be **≤ 2000 characters**.
- Tier 3. `audited_surface: true` because `scripts/office2/deploy/felix-health-check.sh` matches the `systemd-user-units` pattern. No deployed unit content changes, so the expected deployer rebaseline outcome is `cleared_clean` (research F7). Say so in the notes.
- Never `rm -rf`. Retirement is a **move** (`os.replace` / `shutil.move`) into `/data/services/openclaw/felix-health-check/retired/health-check.sh.<YYYYMMDDTHHMMSSZ>`.

## Branch Strategy

- **Planning base branch**: `fix/canary-deadman-backup-coverage` · **Merge target branch**: `fix/canary-deadman-backup-coverage`.

## Subtasks & Detailed Guidance

### Subtask T016 – `scripts/deploy/deploy-health-check-coverage.py`

- `--dry-run` (read-only):
  - emit `preflight` info (user/home are not enforced in dry-run, so it can run from a scratch dir);
  - call `coverage.evaluate_coverage(now)` and emit a `coverage_checks` JSON line;
  - emit `would_run` for `systemctl --user start felix-health-check.service`;
  - emit `would_retire` (or `already_retired`) for `~/helper-scripts/health-check.sh`.
  - Exit 0 if the repo script exists and is executable; else 1.
- `--apply`:
  0. Preflight: euid user `claude` and `Path.home() == /home/claude` (copy from #1062). The repo script at `REPO/scripts/office2/felix_health_check/health-check.sh` exists and is executable.
  1. `t0 = now`. Run `systemctl --user start felix-health-check.service` (oneshot; blocks until done; the unit's `TimeoutStartSec` is 10 min).
  2. Read `/data/services/openclaw/felix-health-check/last-run.json`. Verify **every** item below, collecting all problems; report them all.
     - `ran_at_utc` parses and ≥ `t0` − 5 s (the record is fresh, from this invocation).
     - `script_path` equals the repo script path.
     - `script_status` ∈ {`ALL_HEALTHY`, `FAILURES_DETECTED`} (re-review 2).
     - `exit_code` is an int.
     - `coverage_checks` has exactly the components `felix-canary` and `restic-backup`, and neither entry's `finding` is `unknown` (which covers `unavailable` and `suppressed`) (Codex-2).
     - If `status != "ALL_HEALTHY"`, then `delivery.sent is True` (the alert actually went out).
     - `status` ∈ {`ALL_HEALTHY`, `FAILURES_DETECTED`}.
  3. Any problem → emit `apply_failed` with all problems and exit 1. **Do not retire.**
  4. Retire: if the old path exists, `mkdir -p` the retired directory and move it there (`retired`). If it does not exist, emit `already_retired` (paula-7 idempotency).
  5. Emit `apply_complete` with the verdict summary. Exit 0. A genuine monitored fault (`FAILURES_DETECTED` with the alert delivered) **is a successful deploy**: Kent has been told, which is the point.
- Inject `run`, `now`, `read_text`, `move` and the paths for tests (the #1062 pattern).

### Subtask T017 – `tests/deploy/test_deploy_health_check_coverage.py`

Load the module the way `test_deploy_monotonic_timer_units.py` does. Cases:
- happy path (`ALL_HEALTHY`) → retire called once, exit 0;
- `FAILURES_DETECTED` with `delivery.sent` true → exit 0 and retire;
- `FAILURES_DETECTED` with `delivery.sent` false → exit 1, no retire;
- stale record (`ran_at_utc` < `t0`) → exit 1, no retire;
- `script_path` still the old path → exit 1;
- `script_status` `UNKNOWN` while status `FAILURES_DETECTED` → exit 1 (re-review 2 control);
- a coverage entry missing, or one `unknown` → exit 1;
- `systemctl start` rc ≠ 0 → exit 1;
- already retired → `already_retired`, exit 0;
- wrong user → preflight fails, nothing run.

Assert the move target matches the dated `retired/` pattern, and that `move` is never called on any failure path.

### Subtask T018 – `deploys/queued/health-check-coverage.yaml`

Mirror 0031's shape: `schema_version: v1`, `name: health-check-coverage`, `issue: kentonium3/kg-automation#1063`, `tier: 3`, `entrypoint: scripts/deploy/deploy-health-check-coverage.py`, `audited_surface: true`, `verification.pre: [scripts/deploy/deploy-health-check-coverage.py --dry-run]`.

`verification.post` checks, each a single read-only shell line:
- `test ! -e "$HOME/helper-scripts/health-check.sh"`;
- `jq -e '(.coverage_checks | map(.component) | sort) == ["felix-canary","restic-backup"]' /data/services/openclaw/felix-health-check/last-run.json`;
- `jq -e '.script_path | endswith("scripts/office2/felix_health_check/health-check.sh")' …`;
- `git ls-files -s scripts/office2/felix_health_check/health-check.sh | grep -q ^100755`.

Confirm `jq` exists on office2 (`ssh office2-claude command -v jq`, read-only) before relying on it; otherwise use `python3 -c`.

Also `created_at`, `created_by: claude-code-1063`, and `notes` ≤ 2000 characters covering: what changes, why (#1063), the Tier 3 / audited-surface / `cleared_clean` expectation, rollback (move the retired file back, revert the merge), and that a deploy during a real backup fault succeeds by design once the alert is delivered. Add a test asserting `len(notes) <= 2000` if the deploy tests do not already enforce it.

### Subtask T019 – Repoint the two older references (Codex-7)

- `scripts/office2/deploy/felix-health-check.sh`: set `HEALTH_CHECK_SCRIPT="${REPO_ROOT}/scripts/office2/felix_health_check/health-check.sh"`, and update the messages that call it "the same script the removed openclaw crons invoked". This keeps the refresh script working after retirement.
- `scripts/deploy/deploy-deterministic-monitoring-checks.py` (≈ lines 88, 137): it is an applied record's entrypoint. Repoint its preflight path constant to the repo script, with a one-line comment citing #1063. Do not delete the script. Run its existing tests if any (`grep -rl deterministic_monitoring tests`).
- `bash -n` the shell script.

## Test Strategy

```bash
python3 -m pytest tests/deploy -q
python3 -m pytest -q -x
python3 tooling/scripts/validate_docs.py
```

Pre-merge live dry run (read-only): the quickstart's `git archive … | ssh office2-claude …` command. Record its JSON lines in `add-history`.

## Risks & Mitigations

- **Apply during a genuine fault**: succeeds iff the alert was delivered. A failed delivery is a failed deploy, correctly, because it means nobody was told.
- **Racing the twice-daily timer**: harmless; `t0` filters out a record from an earlier run.
- **Notes too long**: the deployer rejects them, so test the length.

## Review Guidance

- Every failure path asserts `move` not called.
- The post-checks are read-only, and each fails on the pre-deploy state (SC-005 no-op control: the old path exists before the apply).

## Progress & Status

`spec-kitty agent tasks add-history WP04 --note "…"` · implement: `spec-kitty agent action implement WP04 --agent claude --mission canary-deadman-backup-coverage-01M4XVY3`

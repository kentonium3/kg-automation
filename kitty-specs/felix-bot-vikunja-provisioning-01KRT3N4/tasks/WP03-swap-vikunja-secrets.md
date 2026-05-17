---
work_package_id: WP03
title: Swap Vikunja secrets — atomic cutover with auto-rollback
dependencies: []
requirement_refs:
- FR-005
- FR-006
- FR-007
- FR-008
- NFR-002
- NFR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
- T016
history:
- action: drafted
  agent: claude
  timestamp: '2026-05-17T05:20:00Z'
authoritative_surface: scripts/vikunja/swap_vikunja_secrets.py
execution_mode: code_change
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
owned_files:
- scripts/vikunja/swap_vikunja_secrets.py
- tests/vikunja/test_swap_vikunja_secrets.py
tags: []
---

# WP03 — Swap Vikunja secrets atomically with auto-rollback

## Objective

Implement `scripts/vikunja/swap_vikunja_secrets.py` — the cutover-phase helper of ADR-0002 Phase 1 (issue #304). This is the moment-of-truth helper: it atomically rotates `/data/services/openclaw/secrets/vikunja-api` from kent's token to felix-bot's token, restarts `openclaw-gateway.service`, verifies post-swap attribution via a sample Felix agent invocation, and auto-rolls back to the `.bak` on any verification failure.

It also provides an explicit `--rollback-from-bak` mode for operator-triggered rollback during the 7-day soak.

This helper is the single most consequential code in the mission. Its correctness determines whether the rotation succeeds atomically or strands the system in a partial state.

## Context

- **Spec section**: FR-005 (backup), FR-006 (replace), FR-007 (restart), FR-008 (post-swap verify); NFR-002 (downtime < 30 min), NFR-003 (rollback < 5 min), NFR-004 (no errors post-swap) in [spec.md](../spec.md).
- **Design rationale**: [research.md](../research.md) R-005 (atomic write-temp-then-rename pattern), R-006 (operator-driven), R-007 (doc commit timing — after this helper succeeds).
- **API contracts**: See [contracts/vikunja-api-endpoints.md](../contracts/vikunja-api-endpoints.md) section C-11 (post-swap attribution check).
- **File invariants**:
  - `/data/services/openclaw/secrets/vikunja-api` — must remain mode 600, claude:claude throughout
  - `/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak` — created by this helper, mode 600, claude:claude
- **Restart command**: `systemctl --user restart openclaw-gateway` (runs as the `claude` user; the openclaw service is user-systemd, not system-systemd)
- **Existing helper convention**: Same as WP01/WP02.

## Branch strategy

Planning branch: `main`. Final merge target: `main`. Execution worktree allocated per computed lane in `lanes.json` after task finalization.

## Subtask guidance

### T011 — argparse + secrets path validation + atomic-file utility

**Purpose**: Establish the CLI, validate paths, and build the reusable atomic-file utility that backup and rotate both use.

**Steps**:

1. Write the docstring header — emphasize that this is the cutover helper, mention the auto-rollback behavior and the `--rollback-from-bak` mode.
2. Implement argparse with:
   - `--new-token-file` — path to file with felix-bot's token (output of WP01)
   - `--secrets-path` (default `/data/services/openclaw/secrets/vikunja-api`)
   - `--bak-suffix` (default `.kent-pre-felix-bot.bak`)
   - `--gateway-unit` (default `openclaw-gateway.service`) — for systemctl restart
   - `--gateway-health-timeout` (default `30`, type=int) — seconds to wait for gateway
   - `--rollback-from-bak` (boolean flag) — manual rollback mode
   - `--skip-post-verify` (boolean flag) — for debugging, exits 1 if used in non-rollback mode
   - `--dry-run` (boolean flag)
3. Path validations:
   - `--new-token-file` must be readable, mode 600, non-empty
   - `--secrets-path` must exist (we're rotating, not creating)
   - In `--rollback-from-bak` mode, `--bak-path` (computed from secrets-path + suffix) must exist
4. Implement `atomic_write_file(path, content_bytes, mode=0o600, owner='claude', group='claude')`:
   - Write to `path.tmp` (suffix added to caller-provided path), then `os.rename(path.tmp, path)` (atomic on same filesystem)
   - Use `os.open` with `O_WRONLY|O_CREAT|O_TRUNC|O_EXCL` to prevent races; close fd
   - Set mode via `os.chmod(path.tmp, mode)` BEFORE rename (so the target path is never readable by wrong perms)
   - Set ownership via `os.chown` if running as root (typically not the case here — claude:claude is the running user, so chown is a no-op or `os.chown(uid=current, gid=current)`)
   - Return None on success; raise on any error

**Files**:
- `scripts/vikunja/swap_vikunja_secrets.py` (new, ~100 lines for this subtask)

**Validation**:
- `python3 scripts/vikunja/swap_vikunja_secrets.py --help` works
- Path validations trip on missing files
- `atomic_write_file` unit-tested: produces file with mode 600, atomic semantics

### T012 — Atomic backup of existing secrets to .kent-pre-felix-bot.bak

**Purpose**: Before touching the secrets file, copy the existing kent token to a side-by-side `.bak` file. This is the rollback substrate.

**Steps**:

1. Implement `backup_secrets(secrets_path, bak_path) -> dict`:
   - If `bak_path` already exists, exit 1 immediately. Stale .bak indicates a prior incomplete rotation — operator must resolve before proceeding.
   - Read existing `secrets_path` into memory (bytes; do NOT decode as text — preserve any binary).
   - Use `atomic_write_file(bak_path, content_bytes, mode=0o600)` to write the .bak atomically.
   - Verify the .bak was written: read it back, compare size and (optionally) hash against the original. If mismatch, exit 1.
   - Return `{"bak_path": str, "bak_size_bytes": int}` summary.
2. Log every step so the operator sees what's happening: "backing up to {bak_path}", "verified bak: N bytes match".

**Files**:
- `scripts/vikunja/swap_vikunja_secrets.py` (~50 added lines)

**Validation**:
- Unit test mocks an existing secrets file; verifies .bak is written atomically with mode 600.
- Unit test where .bak already exists; helper exits 1 with explicit error.
- Unit test where backup verification fails (mock the readback to differ); helper exits 1.

### T013 — Atomic write of new token + chmod/chown + systemctl restart

**Purpose**: Replace the secrets file with felix-bot's token (atomically), restart the gateway, wait for it to come up healthy.

**Steps**:

1. Implement `rotate_secrets(new_token, secrets_path) -> None`:
   - Read new_token from `--new-token-file`. Validate non-empty.
   - Use `atomic_write_file(secrets_path, new_token, mode=0o600)`.
   - Verify the secrets file now contains the new token (readback equality check).
2. Implement `restart_gateway(unit, health_timeout) -> dict`:
   - `subprocess.run(['systemctl', '--user', 'restart', unit], check=True, capture_output=True, text=True, timeout=30)`. On non-zero return code, raise with the systemctl stderr.
   - Wait for gateway to come up healthy:
     - Poll `systemctl --user is-active {unit}` until it returns `active` or until `health_timeout` seconds pass.
     - On timeout, exit 1 with explicit error.
   - Optionally also probe `openclaw doctor` if available — but `is-active` is the minimum.
   - Return `{"restart_duration_s": N, "is_active": True}`.
3. Sequence: rotate first, then restart. The restart picks up the new secrets file content.

**Files**:
- `scripts/vikunja/swap_vikunja_secrets.py` (~70 added lines)

**Validation**:
- Unit test mocks `atomic_write_file`; verifies secrets file write.
- Unit test mocks `subprocess.run` for systemctl restart; verifies command sequence.
- Unit test mocks `is-active` returning `inactive`; helper polls until timeout; exits 1.
- Unit test mocks systemctl restart failure (non-zero return); helper raises and exits 1.

### T014 — Post-swap attribution verification

**Purpose**: After the rotation succeeds and the gateway restarts, prove that Felix agents now write with felix-bot attribution. This is the success criterion.

**Steps**:

1. Implement `verify_post_swap_attribution(base_url) -> dict`:
   - Invoke a sample Felix agent comment write through the gateway. The simplest path: use `subprocess.run` to call `openclaw agent --to <operator-test-target> --message <test message>` or equivalent. The exact command depends on the gateway's CLI surface.
   - Alternative simpler path that matches the intent: use `urllib.request` to GET `{base_url}/projects/13/tasks?per_page=1` with the NEW token (read from the rotated secrets file). Confirm the GET succeeds (200) — that's the minimal proof felix-bot's token now works.
   - Stronger path: write a test comment to a known low-impact task (e.g., the throwaway task pattern from WP02, but inline here OR by invoking a one-shot Felix-agent script that produces a comment). Verify the comment's `created_by.username == 'felix-bot'`.
   - If verification fails, RAISE — the caller (orchestrate function) catches and triggers auto-rollback.
   - Return `{"verified": True, "comment_attribution": "felix-bot", "task_used": <id>}` on success.

**Files**:
- `scripts/vikunja/swap_vikunja_secrets.py` (~60 added lines)

**Validation**:
- Unit test mocks the GET-projects probe returning 200 and at least 1 project; helper verifies success.
- Unit test mocks the probe returning 401 (token rejected — somehow the rotation failed); helper raises.
- Unit test for the comment-write+attribution probe: full happy path; attribution returned as felix-bot; helper exits 0.
- Unit test where post-swap comment attribution is `kent`; helper raises immediately (caller will trigger rollback).

### T015 — `--rollback-from-bak` mode + auto-rollback on verify failure

**Purpose**: Two rollback paths:
- **Auto**: If T014 verification raises, helper catches, runs rollback, exits 1.
- **Manual**: Operator runs the helper with `--rollback-from-bak` after Phase 5 soak surfaces an issue.

**Steps**:

1. Implement `rollback(secrets_path, bak_path) -> dict`:
   - Verify `bak_path` exists and is readable.
   - Read bak_path into bytes.
   - `atomic_write_file(secrets_path, bak_content, mode=0o600)` — restores kent token.
   - `restart_gateway(unit, health_timeout)` — re-restart the gateway.
   - `verify_post_rollback_attribution(base_url)` — invoke a probe, confirm `created_by.username == 'kent'`. If verification fails post-rollback, this is a deeply degraded state; helper exits 1 with explicit message instructing the operator to investigate manually.
   - Return `{"rolled_back": True, "attribution": "kent"}` on success.
2. Wire the auto-rollback into the main flow:
   ```
   try:
       backup_secrets(...)
       rotate_secrets(...)
       restart_gateway(...)
       verify_post_swap_attribution(...)
   except VerificationFailed:
       print("AUTO-ROLLBACK INITIATED")
       rollback(...)
       sys.exit(1)
   except OtherFailure:
       # rotation may not have happened; check state
       sys.exit(1)
   ```
3. Wire `--rollback-from-bak` mode to directly invoke `rollback(...)` and exit. Path validations apply.

**Files**:
- `scripts/vikunja/swap_vikunja_secrets.py` (~80 added lines)

**Validation**:
- Unit test the full happy path: backup → rotate → restart → verify all succeed; helper exits 0.
- Unit test the auto-rollback path: verify raises; helper catches, restores from .bak, verifies kent attribution restored; exits 1.
- Unit test `--rollback-from-bak` manual mode: helper restores, restarts, verifies kent, exits 0.
- Unit test the deeply degraded state: rollback restore succeeds but post-rollback verification still fails (mock returns felix-bot or unknown); helper exits 1 with the explicit "investigate manually" message.

### T016 — Pytest tests for swap_vikunja_secrets.py

**Purpose**: Comprehensive unit test coverage including the trickier atomic-file logic and the auto-rollback orchestration.

**Steps**:

1. Create `tests/vikunja/test_swap_vikunja_secrets.py`.
2. Test categories:
   - **Argparse + path validation**: missing args, missing files, conflicting flags
   - **`atomic_write_file` utility**: produces correct mode, atomic semantics (using a fixture filesystem)
   - **Backup**: happy path; .bak already exists (exit 1); readback verification fails (exit 1)
   - **Rotate**: secrets file written; readback verifies new content
   - **Restart gateway**: subprocess mock; happy path; timeout path; non-zero return path
   - **Verify attribution**: 200 happy; 401 (token rejected); comment attribution wrong
   - **Auto-rollback orchestration**: verify-raises triggers rollback; full sequence verified
   - **Manual --rollback-from-bak**: happy path
   - **Deeply degraded**: rollback-but-still-broken state exits 1
   - **Dry-run**: no writes, no subprocess calls
3. Aim for ~15-18 tests (this is the largest helper).

**Files**:
- `tests/vikunja/test_swap_vikunja_secrets.py` (new, ~350 lines)

**Validation**:
- `pytest tests/vikunja/test_swap_vikunja_secrets.py -v` all pass
- File-system mutations are tested with `tmp_path` fixture; no real /data/services/openclaw access
- Subprocess calls are mocked

## Test strategy

Pytest with `tmp_path` fixture for filesystem operations + `unittest.mock.patch` for `subprocess.run` and `urllib.request.urlopen`. Same pattern as WP01/WP02 with more emphasis on the filesystem and subprocess mocking.

## Definition of Done

- [ ] `scripts/vikunja/swap_vikunja_secrets.py` exists and is executable
- [ ] `tests/vikunja/test_swap_vikunja_secrets.py` exists with ≥15 passing tests
- [ ] `python3 scripts/vikunja/swap_vikunja_secrets.py --help` works
- [ ] All argparse args from T011 implemented
- [ ] Path validations trip on missing/bad-mode files
- [ ] `atomic_write_file` produces mode 600 files; uses write-temp-then-rename
- [ ] Backup phase writes .bak atomically; exits 1 if .bak already exists
- [ ] Rotate phase writes new token atomically; readback verifies
- [ ] Gateway restart via systemctl --user; waits for is-active up to timeout
- [ ] Post-swap verification probes Vikunja API + confirms attribution
- [ ] Auto-rollback fires on verify failure; restores .bak; re-verifies kent
- [ ] `--rollback-from-bak` mode performs manual rollback symmetrically
- [ ] Deeply-degraded path exits 1 with explicit operator instructions
- [ ] All `SUMMARY:` lines emitted at each phase
- [ ] Pytest suite passes
- [ ] No third-party dependencies

## Risks

- **Race on atomic rename**: Mitigated by `os.rename` atomicity on same filesystem. Source `.tmp` and target are in the same dir.
- **Permission window during chmod**: Mitigated by setting mode on `.tmp` BEFORE rename (file is never visible at target path with wrong perms).
- **Gateway slow to start**: `--gateway-health-timeout` default 30s with poll loop; can be raised via flag.
- **Verify probe transient failure**: A single GET-projects probe may falsely fail on transient network/timing issues. Retry once before triggering rollback? Consider; the current spec says fail-fast for safety. Could add a 1-retry-with-1-sec-delay to be more robust without losing the safety property.
- **Auto-rollback during partial state**: If the rotate succeeds but the restart fails midway, the system is in a state where the new token is in the file but the gateway is restarting. Helper's rollback path tolerates this (it restores .bak content and restarts again).

## Reviewer guidance (for Codex review)

- Verify `atomic_write_file` truly uses write-temp-then-rename. The temp file must be in the same directory as the target (so rename is atomic on the same filesystem).
- Verify `os.chmod` happens BEFORE the rename — there must be no window where the target path is visible with the default umask permissions.
- Verify the .bak file is created BEFORE the rotate. The order matters for rollback safety.
- Verify the auto-rollback handler catches the specific verification-failed exception, not a blanket Exception (or if blanket, it logs the original exception clearly).
- Verify the post-rollback verification confirms `created_by.username == 'kent'` — not just "the call succeeded."
- Verify systemctl is invoked as `--user`, not system-wide.
- Verify dry-run mode does ZERO subprocess calls AND ZERO HTTP calls AND ZERO file writes (use mocks to assert).
- Confirm the SUMMARY line at each phase boundary is parseable.
- Confirm timeout semantics: if gateway takes 35s to come up and timeout is 30s, helper exits 1 (does not silently continue).

## Implementation command

```bash
spec-kitty agent action implement WP03 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent <tool>:<model>:<profile>:<role>
```

## Review command

```bash
spec-kitty agent action review WP03 --mission felix-bot-vikunja-provisioning-01KRT3N4 --agent codex:gpt-4o:python-reviewer:reviewer
```

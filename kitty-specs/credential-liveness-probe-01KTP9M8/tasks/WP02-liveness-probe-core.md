---
work_package_id: WP02
title: Liveness probe core (probe_oauth_liveness + LivenessResult)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-019
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-005
- NFR-007
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
- T012
agent: claude
history: []
agent_profile: python-pedro
authoritative_surface: scripts/security/credential_health_check/
execution_mode: code_change
mission_id: 01KTP9M86VF89TQM5SX7JVA83Z
mission_slug: credential-liveness-probe-01KTP9M8
owned_files:
- scripts/security/credential_health_check/liveness.py
- tests/security/credential_health_check/test_liveness.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Python implementer posture: stdlib-only, test-first, locality of change.

## Objective

Create `scripts/security/credential_health_check/liveness.py` containing the `LivenessResult` dataclass and the `probe_oauth_liveness()` function. Pure logic helper with no orchestrator integration (deferred to WP03). All 13 contract test cases pass with ≥90% line / ≥85% branch coverage.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Lane worktree: allocated per `lanes.json` after `finalize-tasks` runs. Parallel-safe with WP01 (different files). Lane base computed from dependencies (none for this WP).

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | FR-001..007, FR-019, NFR-001..007 |
| [../plan.md](../plan.md) § IC-01 | Concern map; risks; ±24h boundary edge testing |
| [../data-model.md](../data-model.md) § LivenessResult | Dataclass shape + invariants |
| [../research.md](../research.md) Decisions 1, 2, 7 | Why this probe call shape; why ±24h; why mock not live |
| [../contracts/liveness-probe-function.md](../contracts/liveness-probe-function.md) | Function signature, behavior pseudo-code, 13 test cases |
| `scripts/security/credential_health_check/signals.py` | Existing pattern for `ActivitySignalFailure` (mirror for `LivenessResult`) |
| `scripts/security/credential_health_check/manifest.py` | `Credential` dataclass (after WP01 lands) |
| `tests/security/credential_health_check/test_signals.py` | Subprocess + JSON mocking patterns to mirror |

## Subtask Guidance

### T006 — Create `liveness.py` skeleton + `LivenessResult` dataclass

**Steps**:

1. Create new file `scripts/security/credential_health_check/liveness.py`.
2. Module docstring referencing #572 + the contract path.
3. Imports:

   ```python
   from __future__ import annotations

   import logging
   import subprocess
   import time
   from dataclasses import dataclass
   from datetime import datetime, timedelta, timezone
   from pathlib import Path
   from typing import Literal, Optional
   ```

4. Define the classification literal:

   ```python
   LivenessClassification = Literal[
       "dead-routine-7day",
       "dead-unexpected",
       "probe-error",
   ]
   ```

5. Define the dataclass per data-model.md:

   ```python
   @dataclass(frozen=True)
   class LivenessResult:
       """Per-credential probe outcome. Returned only on failure or error.

       Alive credentials return None from probe_oauth_liveness().
       """
       credential_name: str
       classification: LivenessClassification
       reason: str
       recovery_command: Optional[str]
       probed_at: datetime  # MUST be timezone-aware UTC
   ```

6. Module-level constants:

   ```python
   GOG_BINARY = "/home/linuxbrew/.linuxbrew/bin/gog"
   PROBE_TIMEOUT_SECONDS = 15
   CYCLE_WINDOW_HOURS = 24  # ±24h around mtime + 7d for routine classification
   EXPECTED_TTL_DAYS = 7
   ```

7. Module-level logger:

   ```python
   _logger = logging.getLogger("credential_health_check.liveness")
   ```

**Files**:
- `scripts/security/credential_health_check/liveness.py` (new, ~40 lines so far)

**Validation**:
- `python3 -c "from credential_health_check.liveness import LivenessResult, probe_oauth_liveness, LivenessClassification; print('ok')"` — well, `probe_oauth_liveness` not defined yet; just check `LivenessResult` import.

---

### T007 — Implement `probe_oauth_liveness()` happy-path

**Steps**:

1. Add function signature with the contract's positional + kwarg shape:

   ```python
   def probe_oauth_liveness(
       credential,  # Credential (forward-ref to avoid circular import)
       *,
       now_utc: Optional[datetime] = None,
   ) -> Optional[LivenessResult]:
       """Probe a single oauth2 credential for liveness.

       See kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md
       for the full contract.
       """
   ```

2. Defensive assertion (caller is responsible for filtering, but assert as safety net):

   ```python
   if credential.liveness_probe is None or not credential.liveness_probe.enabled:
       raise ValueError(
           f"probe_oauth_liveness called on credential {credential.name!r} "
           f"with no enabled liveness_probe block"
       )
   ```

3. Compute `now`:

   ```python
   now = now_utc or datetime.now(timezone.utc)
   if now.tzinfo is None:
       raise ValueError("now_utc must be timezone-aware")
   ```

4. Pull config + run probe:

   ```python
   cfg = credential.liveness_probe
   t0 = time.monotonic()
   try:
       result = subprocess.run(
           [
               GOG_BINARY,
               "--account", cfg.gog_account,
               "calendar", "list",
               "-j",
               "--max-results", "1",
           ],
           capture_output=True,
           text=True,
           timeout=PROBE_TIMEOUT_SECONDS,
       )
   except subprocess.TimeoutExpired:
       # Handled in T009; placeholder pass for now.
       raise
   except FileNotFoundError:
       # Handled in T009.
       raise
   duration_ms = int((time.monotonic() - t0) * 1000)
   ```

5. Happy-path branch:

   ```python
   if result.returncode == 0:
       _logger.info(
           "credential_alive credential_name=%s probed_at=%s duration_ms=%d",
           credential.name,
           now.isoformat(),
           duration_ms,
       )
       return None
   ```

**Files**:
- `scripts/security/credential_health_check/liveness.py` (+~50 lines)

**Validation**:
- After T011 tests are written, `test_alive_returns_none` passes.

---

### T008 — `invalid_grant` detection + classification window

**Steps**:

1. After the rc==0 check, add the `invalid_grant` branch:

   ```python
   if "invalid_grant" in (result.stderr or ""):
       keyring_path = Path(cfg.keyring_file)
       try:
           mtime_ts = keyring_path.stat().st_mtime
       except FileNotFoundError:
           # Keyring file missing — treat as probe-error, not dead.
           return LivenessResult(
               credential_name=credential.name,
               classification="probe-error",
               reason=f"keyring file not found at {cfg.keyring_file}",
               recovery_command=None,
               probed_at=now,
           )
       mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
       expected_expiration = mtime + timedelta(days=EXPECTED_TTL_DAYS)
       delta = abs(now - expected_expiration)
       if delta <= timedelta(hours=CYCLE_WINDOW_HOURS):
           classification = "dead-routine-7day"
           reason = (
               f"Token expired at the 7-day Testing-app cycle boundary "
               f"(mtime+7d={expected_expiration.isoformat()}, "
               f"delta={delta}). Run the recovery command to re-mint."
           )
       else:
           classification = "dead-unexpected"
           reason = (
               f"Token died at non-cycle time "
               f"(mtime+7d={expected_expiration.isoformat()}, "
               f"delta={delta}). "
               f"If you didn't recently change passwords or revoke access, "
               f"investigate at https://myaccount.google.com/permissions "
               f"before re-auth."
           )
       _logger.info(
           "credential_dead credential_name=%s classification=%s "
           "probed_at=%s duration_ms=%d reason=%s recovery_command=%s",
           credential.name,
           classification,
           now.isoformat(),
           duration_ms,
           reason,
           cfg.recovery_command,
       )
       return LivenessResult(
           credential_name=credential.name,
           classification=classification,
           reason=reason,
           recovery_command=cfg.recovery_command,
           probed_at=now,
       )
   ```

**Files**:
- `scripts/security/credential_health_check/liveness.py` (+~45 lines)

**Validation**:
- `test_dead_routine_7day`, `test_dead_unexpected_too_early`, `test_dead_unexpected_too_late`, `test_routine_boundary_just_inside`, `test_routine_boundary_just_outside`, `test_recovery_command_in_dead_result` pass after T011.

---

### T009 — Probe-error branches

**Steps**:

1. Move the `TimeoutExpired` + `FileNotFoundError` catches OUT of `raise` and INTO handlers. Refactor the `subprocess.run` block:

   ```python
   try:
       result = subprocess.run(...)
   except subprocess.TimeoutExpired:
       duration_ms = int((time.monotonic() - t0) * 1000)
       reason = f"liveness probe exceeded {PROBE_TIMEOUT_SECONDS}s timeout"
       _logger.info(
           "credential_probe_error credential_name=%s probed_at=%s "
           "duration_ms=%d error_detail=%s",
           credential.name, now.isoformat(), duration_ms, reason,
       )
       return LivenessResult(
           credential_name=credential.name,
           classification="probe-error",
           reason=reason,
           recovery_command=None,
           probed_at=now,
       )
   except FileNotFoundError:
       duration_ms = int((time.monotonic() - t0) * 1000)
       reason = f"gog binary not found at {GOG_BINARY}"
       _logger.info(... )
       return LivenessResult(
           credential_name=credential.name,
           classification="probe-error",
           reason=reason,
           recovery_command=None,
           probed_at=now,
       )
   ```

2. After the `rc==0` and `invalid_grant` branches, add the "other non-zero" fallthrough:

   ```python
   reason = (
       f"gog exited {result.returncode}: "
       f"{(result.stderr or '').strip()[:200]}"
   )
   _logger.info(
       "credential_probe_error credential_name=%s probed_at=%s "
       "duration_ms=%d error_detail=%s",
       credential.name, now.isoformat(), duration_ms, reason,
   )
   return LivenessResult(
       credential_name=credential.name,
       classification="probe-error",
       reason=reason,
       recovery_command=None,
       probed_at=now,
   )
   ```

3. Watch closely: in the `invalid_grant` branch above, the keyring-file-missing case ALSO returns `probe-error` (not a dead classification). The `recovery_command` is `None` for ALL probe-error cases.

**Files**:
- `scripts/security/credential_health_check/liveness.py` (+~30 lines)

**Validation**:
- `test_probe_timeout`, `test_probe_missing_binary`, `test_probe_other_failure`, `test_recovery_command_none_in_probe_error` pass after T011.

---

### T010 — Structured INFO logging (verify)

This is mostly woven into T007–T009. Verify each branch emits exactly ONE structured log line:

| Branch | Event name | Required fields |
|---|---|---|
| rc==0 | `credential_alive` | credential_name, probed_at, duration_ms |
| `invalid_grant` + within window | `credential_dead` (classification=dead-routine-7day) | + classification, reason, recovery_command |
| `invalid_grant` + outside window | `credential_dead` (classification=dead-unexpected) | + classification, reason, recovery_command |
| `TimeoutExpired` | `credential_probe_error` | + error_detail |
| `FileNotFoundError` | `credential_probe_error` | + error_detail |
| other non-zero | `credential_probe_error` | + error_detail |
| keyring missing | `credential_probe_error` | + error_detail |

**Validation**:
- Add `caplog` (pytest fixture) assertions in a smoke test (one assertion per branch) to confirm event names.

**Files**:
- `scripts/security/credential_health_check/liveness.py` (no new code; verification only)

---

### T011 — Create `test_liveness.py` with 13 contract test cases

**Probe first**:

```bash
grep -n "def test_\|monkeypatch\|subprocess" tests/security/credential_health_check/test_signals.py
```

**Steps**:

1. Create `tests/security/credential_health_check/test_liveness.py`.
2. Test helper to build a `Credential` with a populated `liveness_probe`:

   ```python
   import json, subprocess
   from datetime import datetime, timedelta, timezone
   from pathlib import Path

   import pytest

   from credential_health_check.liveness import (
       LivenessResult,
       probe_oauth_liveness,
   )
   from credential_health_check.manifest import Credential, LivenessProbeConfig


   def make_credential(tmp_path, *, enabled=True):
       keyring = tmp_path / "keyring_file"
       keyring.write_bytes(b"")  # real file for stat()
       return Credential(
           name="gog-credentials-keyring",
           # ...fill remaining required fields per Credential dataclass...
           liveness_probe=LivenessProbeConfig(
               enabled=enabled,
               gog_account="kentgale@gmail.com",
               keyring_file=str(keyring),
               recovery_command="ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh",
           ),
       )
   ```

3. Test functions, one per contract row:

   - `test_alive_returns_none(tmp_path, monkeypatch)` — mock subprocess.run rc=0; assert None.
   - `test_dead_routine_7day(tmp_path, monkeypatch)` — mock rc=1 + stderr `invalid_grant`; set keyring mtime to (now - 6.9 days) via `os.utime`; assert `dead-routine-7day`.
   - `test_dead_unexpected_too_early(tmp_path, monkeypatch)` — mtime = now - 3 days; assert `dead-unexpected`.
   - `test_dead_unexpected_too_late(tmp_path, monkeypatch)` — mtime = now - 9 days; assert `dead-unexpected`.
   - `test_routine_boundary_just_inside(tmp_path, monkeypatch)` — mtime = now - 7d - 23h; assert `dead-routine-7day`.
   - `test_routine_boundary_just_outside(tmp_path, monkeypatch)` — mtime = now - 7d - 25h; assert `dead-unexpected`.
   - `test_probe_timeout(tmp_path, monkeypatch)` — mock `subprocess.run` to raise `TimeoutExpired`; assert `probe-error` with "15s" in reason.
   - `test_probe_missing_binary(tmp_path, monkeypatch)` — mock `subprocess.run` to raise `FileNotFoundError`; assert `probe-error` with "gog binary not found".
   - `test_probe_other_failure(tmp_path, monkeypatch)` — mock rc=2 + stderr "boom"; assert `probe-error` with exit code in reason.
   - `test_recovery_command_in_dead_result(tmp_path, monkeypatch)` — dead-routine case; assert `result.recovery_command == credential.liveness_probe.recovery_command`.
   - `test_recovery_command_none_in_probe_error(tmp_path, monkeypatch)` — probe-error case; assert `result.recovery_command is None`.
   - `test_raises_if_liveness_probe_disabled(tmp_path)` — `enabled=False`; assert `pytest.raises(ValueError)`.
   - `test_probed_at_is_utc(tmp_path, monkeypatch)` — any case; assert `result.probed_at.tzinfo == timezone.utc`.

4. Subprocess mocking pattern:

   ```python
   def make_subprocess_run(returncode=0, stdout="", stderr="", side_effect=None):
       def fake_run(*args, **kwargs):
           if side_effect:
               raise side_effect
           return subprocess.CompletedProcess(
               args=args[0], returncode=returncode,
               stdout=stdout, stderr=stderr,
           )
       return fake_run

   def test_alive_returns_none(tmp_path, monkeypatch):
       cred = make_credential(tmp_path)
       monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=0))
       assert probe_oauth_liveness(cred) is None
   ```

5. Mtime control via `os.utime(path, (atime, mtime))`:

   ```python
   import os
   from datetime import datetime, timedelta, timezone

   now = datetime.now(timezone.utc)
   mtime_dt = now - timedelta(days=6, hours=22)
   os.utime(str(keyring_path), (mtime_dt.timestamp(), mtime_dt.timestamp()))
   ```

   Alternatively pass `now_utc=` to the function and keep the file's mtime fixed.

**Files**:
- `tests/security/credential_health_check/test_liveness.py` (new, ~250 lines)

**Validation**:
- `pytest tests/security/credential_health_check/test_liveness.py -v` — all 13 tests pass.

---

### T012 — Verify coverage gate

**Steps**:

```bash
cd /Users/kentgale/repos/kg-automation
PYTHONPATH=scripts/security pytest tests/security/credential_health_check/test_liveness.py \
  --cov=scripts.security.credential_health_check.liveness \
  --cov-branch --cov-fail-under=90 -v
```

If coverage is below the gate:

1. Identify the missing line/branch from the coverage report.
2. Add a test that exercises it OR mark unreachable defensive guards with `# pragma: no cover` / `# pragma: no branch` per `[[reference_pytest_branch_coverage_pragma]]`.
3. Re-run.

**Validation**:
- Exit 0 from the pytest command.
- Coverage report shows `liveness.py` at ≥90% line / ≥85% branch.

---

## Test Strategy

All tests live in `tests/security/credential_health_check/test_liveness.py`. Subprocess + filesystem mocking only — NO real `gog` calls (per Decision 7 in research.md). Coverage gate is enforced. Existing tests in the package STAY passing.

## Definition of Done

- [ ] `scripts/security/credential_health_check/liveness.py` exists.
- [ ] `LivenessClassification` literal, `LivenessResult` dataclass (frozen), and `probe_oauth_liveness` function are exported.
- [ ] All 7 logical branches (alive / dead-routine / dead-unexpected / timeout / missing-binary / other-non-zero / keyring-missing) are reachable + test-covered.
- [ ] 13 test cases pass.
- [ ] Coverage gate `--cov-fail-under=90` passes for `liveness.py`.
- [ ] `pytest tests/security/credential_health_check/ -v` — all tests in the package pass (no regressions).
- [ ] No real `gog` subprocess invocation during pytest.
- [ ] Structured INFO log lines emit one per branch with the required fields.

## Risks

- **Subprocess mocking footgun**: `monkeypatch.setattr(subprocess, "run", fake_run)` is the right call site; do NOT monkeypatch `Popen` (lower-level, won't match the call).
- **Cycle boundary tests**: write the mtime delta with care — `timedelta(days=6, hours=23, minutes=59)` is "just inside"; `timedelta(days=7, hours=24, minutes=1)` is "just outside" (note the asymmetry — within ±24h of `mtime + 7d`).
- **Frozen dataclass**: `LivenessResult` is `frozen=True`; tests must not mutate its fields after construction.
- **Branch coverage**: defensive branches (e.g., `now.tzinfo is None`) may be hard to hit naturally; use `# pragma: no branch` per the memory entry if the orchestrator's defensive call sites guarantee unreachability.

## Reviewer Guidance

- The probe is pure-ish (depends on subprocess + filesystem). All non-stdlib dependencies are clearly mockable.
- Every branch returns exactly one of: `None`, `LivenessResult(classification=dead-routine-7day)`, `LivenessResult(classification=dead-unexpected)`, `LivenessResult(classification=probe-error)`. There is no fall-through path.
- `recovery_command` is populated for `dead-*` and `None` for `probe-error`. Test asserts both.
- Coverage gate is meaningful — reviewer should verify it actually runs against `liveness.py` and not just the test file.

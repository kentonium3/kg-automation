---
work_package_id: WP03
title: Activity signal readers (tailscale + whatsapp)
dependencies:
- WP01
requirement_refs:
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
agent: "claude"
shell_pid: "22433"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/security/credential_health_check/signals.py
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/signals.py
- tests/security/test_tailscale_signal.py
- tests/security/test_whatsapp_signal.py
tags: []
---

# WP03 — Activity signal readers

## Objective

Implement the two `monitor-activity` signal readers per the A-004 resolution: `tailscale-auth` (via `tailscale status --json`) and `whatsapp-session` (via `openclaw channels status`). Each reader returns either `None` (signal healthy) or an `ActivitySignalFailure` describing why an alert should fire.

## Context

- **Spec** anchor: FR-003 (`monitor-activity` credentials use a different alert path than cadence-based ones).
- **Research** anchor: R-001 (probed live: both signals are programmatic and queryable from `claude` user without sudo).
- **Contracts** anchor: `contracts/activity-signal-readers.md` is the authoritative spec.
- **Data-model** anchor: `ActivitySignal` entity; `ActivitySignalFailure` shape.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main` per the spec-kitty flow.

## Subtasks

### T011 — `signals.py` skeleton

**Purpose**: Define shared types and the reader registry.

**Steps**:

1. Create `scripts/security/credential_health_check/signals.py` with:
   ```python
   from dataclasses import dataclass
   from typing import Callable, Optional
   from .manifest import Credential

   @dataclass(frozen=True)
   class ActivitySignalFailure:
       """Returned by a signal reader when an alert should fire for a monitor-activity credential."""
       credential_name: str
       reason: str       # Human-readable explanation for the issue body.
       summary: str      # One-line summary for log lines.

   SignalReader = Callable[[Credential], Optional[ActivitySignalFailure]]

   # Populated by the imports of tailscale_auth_signal and whatsapp_session_signal below.
   MONITOR_ACTIVITY_READERS: dict[str, SignalReader] = {}
   ```
2. After defining the two reader functions (T012, T013), register them at the bottom of the module:
   ```python
   MONITOR_ACTIVITY_READERS["tailscale-auth"] = tailscale_auth_signal
   MONITOR_ACTIVITY_READERS["whatsapp-session"] = whatsapp_session_signal
   ```

**Files**: `scripts/security/credential_health_check/signals.py` (initial structure).

---

### T012 — `tailscale_auth_signal`

**Purpose**: Detect "Tailscale backend not Running" per `contracts/activity-signal-readers.md` §Reader 1.

**Steps**:

1. Implement:
   ```python
   import subprocess, json

   def tailscale_auth_signal(credential: Credential) -> Optional[ActivitySignalFailure]:
       try:
           result = subprocess.run(
               ["tailscale", "status", "--json"],
               capture_output=True, text=True, timeout=5
           )
       except subprocess.TimeoutExpired:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason="tailscale status command timed out after 5 seconds.",
               summary="tailscale: command timeout",
           )
       if result.returncode != 0:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason=f"tailscale status exited {result.returncode}: {result.stderr.strip()[:200]}",
               summary=f"tailscale: exit {result.returncode}",
           )
       try:
           data = json.loads(result.stdout)
       except json.JSONDecodeError as e:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason=f"tailscale status output was not valid JSON: {e}",
               summary="tailscale: malformed JSON",
           )
       backend_state = data.get("BackendState", "<missing>")
       if backend_state != "Running":
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason=f"Tailscale BackendState is `{backend_state}`, expected `Running`. Inspect with: tailscale status",
               summary=f"tailscale: BackendState={backend_state}",
           )
       return None
   ```

**Files**: `scripts/security/credential_health_check/signals.py` (modify).

---

### T013 — `whatsapp_session_signal` + duration parser

**Purpose**: Detect not-connected or stale WhatsApp session per §Reader 2.

**Steps**:

1. Implement the duration parser:
   ```python
   import re
   from datetime import timedelta

   _DURATION_PATTERN = re.compile(r"(?:(\d+)w)?\s*(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?")

   def parse_duration(s: str) -> Optional[timedelta]:
       """Parse durations like '38m', '2h 14m', '3d 5h', '2w' (from openclaw output) into timedelta. Returns None on parse failure."""
       s = s.strip().rstrip("ago").strip()
       m = _DURATION_PATTERN.fullmatch(s)
       if not m or not any(m.groups()):
           return None
       w, d, h, mi, se = (int(x) if x else 0 for x in m.groups())
       return timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=se)
   ```
2. Implement the signal reader:
   ```python
   def whatsapp_session_signal(credential: Credential) -> Optional[ActivitySignalFailure]:
       try:
           result = subprocess.run(
               ["openclaw", "channels", "status"],
               capture_output=True, text=True, timeout=10,
           )
       except subprocess.TimeoutExpired:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason="openclaw channels status timed out after 10 seconds.",
               summary="whatsapp: command timeout",
           )
       if result.returncode != 0:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason=f"openclaw channels status exited {result.returncode}: {result.stderr.strip()[:200]}",
               summary=f"whatsapp: exit {result.returncode}",
           )
       # Find the WhatsApp default channel line.
       channel_line = next(
           (l for l in result.stdout.splitlines() if "WhatsApp default" in l),
           None,
       )
       if channel_line is None:
           return ActivitySignalFailure(
               credential_name=credential.name,
               reason="openclaw channels status output did not include a 'WhatsApp default' channel line.",
               summary="whatsapp: channel missing from status",
           )
       # Extract flags.
       for flag in ("linked", "running", "connected"):
           if flag not in channel_line.split(","):
               # Actually we want a more careful match — see implementation note below.
               pass
       # See below for the careful flag + duration extraction.
       ...
       return None  # if all checks pass
   ```
3. Implementation note for the flag matching: the channel line looks like:
   ```
   - WhatsApp default: enabled, configured, linked, running, connected, in:38m ago, out:38m ago, dm:allowlist, allow:+16179300916
   ```
   Split on comma, strip whitespace, check membership of `"linked"`, `"running"`, `"connected"` in the resulting token set. For the `in:` and `out:` markers, scan for a token starting with `in:` or `out:`, strip the prefix, and pass to `parse_duration`. Apply thresholds: > 14 days → alert.

**Files**: `scripts/security/credential_health_check/signals.py` (modify — add duration parser + reader + register).

---

### T014 — Tests for `tailscale_auth_signal`

**Purpose**: Verify decisions against the three tailscale fixtures.

**Steps**:

1. Create `tests/security/test_tailscale_signal.py`.
2. Use `unittest.mock.patch` to stub `subprocess.run` returning a `CompletedProcess` whose `stdout` is the fixture file content.
3. Cases:
   - `test_running_fixture_returns_none`: stub with `tailscale-status-running.json` content → `tailscale_auth_signal()` returns `None`.
   - `test_needs_login_fixture_alerts`: stub with `tailscale-status-needs-login.json` content → returns `ActivitySignalFailure` with `reason` containing `"NeedsLogin"`.
   - `test_stopped_fixture_alerts`: similar for `Stopped`.
   - `test_subprocess_failure_alerts`: stub returns `returncode=1` → returns failure with the right reason.
   - `test_subprocess_timeout_alerts`: stub raises `TimeoutExpired` → returns failure.
   - `test_malformed_json_alerts`: stub returns garbage `stdout` → returns failure mentioning JSON.

**Files**: `tests/security/test_tailscale_signal.py` (create, ~100 lines).

---

### T015 — Tests for `whatsapp_session_signal` + duration parser

**Purpose**: Verify decisions against the three openclaw fixtures + duration-parser correctness.

**Steps**:

1. Create `tests/security/test_whatsapp_signal.py`.
2. Duration parser tests (one parametric `pytest` fixture):
   - `"38m"` → `timedelta(minutes=38)`
   - `"2h 14m"` → `timedelta(hours=2, minutes=14)`
   - `"3d 5h"` → `timedelta(days=3, hours=5)`
   - `"2w"` → `timedelta(weeks=2)` (= 14 days)
   - `"38m ago"` (with trailing `ago`) → `timedelta(minutes=38)`
   - `"bogus"` → `None`
3. Signal-reader tests (mock `subprocess.run`):
   - `test_healthy_fixture_returns_none`: against `openclaw-channels-status-healthy.txt`.
   - `test_not_connected_alerts`: against `openclaw-channels-status-not-connected.txt` → `reason` mentions "not connected".
   - `test_stale_in_activity_alerts`: against `openclaw-channels-status-stale.txt` → `reason` mentions `in:` and 14-day threshold.

**Files**: `tests/security/test_whatsapp_signal.py` (create, ~120 lines).

---

## Definition of Done

- All five subtasks complete.
- `python -m pytest tests/security/test_tailscale_signal.py tests/security/test_whatsapp_signal.py -v` → all green.
- `signals.py` exports `MONITOR_ACTIVITY_READERS` populated with both readers under the credential `name` keys.
- Commit prefix: `feat(security):` or `feat(WP03):` referencing #115.

## Risks

- **`openclaw channels status` output format**: parsed via regex/split — if openclaw upstream changes the line format, the parser breaks. The captured fixture (`openclaw-channels-status-healthy.txt`) anchors against drift; tests will fail loudly.
- **Timeout values**: `tailscale status --json` is typically sub-second; 5s is generous. `openclaw channels status` involves a gateway probe that can be slower; 10s is the recommended ceiling.
- **`subprocess` mocking in tests**: stub at the `subprocess.run` boundary, not deeper. Use `unittest.mock.patch("scripts.security.credential_health_check.signals.subprocess.run", ...)` or equivalent.

## Reviewer guidance

- Verify: every alert path returns an `ActivitySignalFailure` with both `reason` (human-readable, used in issue body) and `summary` (short, used in log lines).
- Verify: the duration parser handles `2w` correctly (14 days, exactly at threshold) — neither over- nor under-alerts.
- Verify: the signal-reader function for each credential is registered in `MONITOR_ACTIVITY_READERS` keyed by credential `name`, not credential `type`.
- Verify: timeouts are explicit (no implicit-infinite subprocess.run calls).

## Suggested implement command

```bash
spec-kitty agent action implement WP03 --agent <name>
```

## Activity Log

- 2026-05-11T22:01:49Z – claude – shell_pid=22433 – Started implementation via action command
- 2026-05-11T22:03:32Z – claude – shell_pid=22433 – 59/59 tests pass; signal readers handle all failure modes per contract.

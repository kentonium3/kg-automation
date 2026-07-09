---
work_package_id: WP01
title: Calendar auth module — per-account load/refresh/persist, fail-safe
dependencies: []
requirement_refs:
- FR-005
- FR-006
- NFR-002
- NFR-004
tracker_refs: []
planning_base_branch: feat/felix-calendar-helper
merge_target_branch: feat/felix-calendar-helper
branch_strategy: Planning artifacts for this mission were generated on feat/felix-calendar-helper. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-calendar-helper unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
agent: "claude:opus:python-pedro:implementer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/google/calendar_auth.py
create_intent:
- scripts/google/calendar_auth.py
- tests/google/test_calendar_auth.py
- tests/google/__init__.py
execution_mode: code_change
mission_id: 01KX4H3C4CZ2W0DRSHZHSNAY53
mission_slug: felix-calendar-helper-01KX4H3C
owned_files:
- scripts/google/calendar_auth.py
- tests/google/test_calendar_auth.py
- tests/google/__init__.py
role: implementer
tags: []
shell_pid: "45344"
---

# WP01 — Calendar auth module (per-account, fail-safe)

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Then continue.

## Branch Strategy

- **Planning/base branch**: `feat/felix-calendar-helper`
- **Final merge target**: `feat/felix-calendar-helper`
- Execution workspace is resolved by `/spec-kitty.implement`; trust the path it prints. If human instructions contradict these fields, stop and resolve first.

## Objective

Build a small, unit-testable authentication module `scripts/google/calendar_auth.py`
that the calendar helper (WP02) imports. It resolves **per-account** OAuth
credentials and returns valid Google `Credentials`, **failing safe** on any auth
problem. This generalizes the proven pattern in
`scripts/google/workspace_auth_spike.py` (read it first — reuse
`_load_or_mint`/`_write_token` shape).

Authoritative detail: `../data-model.md` (Account, OAuth credential) and
`../research.md` D1/D5/D7. Do not exceed this scope.

## Subtasks

### T001 — Per-account credential path resolution + guards
- `credential_dir(account: str) -> Path` resolving `FELIX_GOOGLE_DIR`
  (default `~/.config/felix/google`) `/ <account>`; default account `personal`.
- Validate `account` against `^[a-z0-9][a-z0-9_-]*$`; raise `ValueError` (→ helper
  exit 2) on violation to prevent path traversal.
- `client_secret_path` / `token_path` helpers. On write, ensure dir `0700`, file
  `0600` (mirror the spike's `_write_token`).

### T002 — Load / refresh / persist + fail-safe
- `load_credentials(account: str, scopes: list[str]) -> Credentials`:
  - Load `token.json` if present (`Credentials.from_authorized_user_file`).
  - If valid → return. If expired **and** has `refresh_token` → `creds.refresh(Request())`,
    persist, return.
  - On **any** failure (missing token, invalid token, `RefreshError`/`invalid_grant`,
    no refresh_token) → raise a typed `CalendarAuthError` carrying an actionable
    message (`"re-mint token on the Mac for account '<a>' with scope <X>"`).
  - **Never** run an interactive consent flow here — office2 is headless. (The
    interactive mint stays a Mac-side operator step; this module only loads/refreshes.)
- Expose `SCOPES_DEFAULT = ["https://www.googleapis.com/auth/calendar.events"]`.
- Persist refreshed tokens atomically (temp + `os.replace`, `0600`) — never print token contents.

### T003 — Tests (`tests/google/test_calendar_auth.py`, + `tests/google/__init__.py`)
**CI-safe imports (important)**: the google libs are NOT in `requirements.txt`
(they live only in the office2 venv), so CI won't have them. Make the module
import cleanly without them — do google imports **lazily** inside functions, and
in tests inject fakes via `sys.modules` (`google`, `google.oauth2.credentials`,
`google.auth.transport.requests`, `googleapiclient.discovery`) before importing
the module. The unit tests must pass with **no** google packages installed.
Mock `Credentials` and the refresh transport (do **not** rely on the urlopen
block — google uses other transports). Cover:
- valid token → returned unchanged;
- expired-but-refreshable → `refresh` called + persisted;
- `invalid_grant`/`RefreshError` → `CalendarAuthError` (no interactive flow attempted);
- missing token → `CalendarAuthError` with re-mint message;
- account path resolution honors `FELIX_GOOGLE_DIR`; bad account name → `ValueError`;
- persisted file perms are `0600` (or assert the chmod call).

## Definition of Done
- [ ] `scripts/google/calendar_auth.py` implements the three concerns above; no interactive consent path.
- [ ] `CalendarAuthError` typed exception exists and carries an actionable message.
- [ ] `pytest tests/google/test_calendar_auth.py --cov=scripts.google.calendar_auth --cov-branch` passes at/above repo threshold; no network.
- [ ] No secrets printed; token writes are atomic + `0600`.

## Risks / reviewer guidance
- Verify the fail-safe: there is **no** code path that opens a browser / local server on office2.
- Confirm charset guard blocks `../` and absolute-path account names.
- Confirm scope constant matches `calendar.events` (data-model D-note) — the helper's self-check must work with it.

## Activity Log

- 2026-07-09T23:25:09Z – claude:opus:python-pedro:implementer – shell_pid=45344 – Assigned agent via action command

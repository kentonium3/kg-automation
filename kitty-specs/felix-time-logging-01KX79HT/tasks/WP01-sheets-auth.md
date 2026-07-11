---
work_package_id: WP01
title: Sheets auth (per-account, spreadsheets scope)
dependencies: []
requirement_refs:
- C-002
tracker_refs: []
planning_base_branch: feat/felix-time-logging
merge_target_branch: feat/felix-time-logging
branch_strategy: Planning artifacts for this mission were generated on feat/felix-time-logging. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-time-logging unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
phase: Phase 1 - Auth
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: "python-pedro"
shell_pid: "41877"
history:
- at: '2026-07-10T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/google/
create_intent:
- scripts/google/sheets_auth.py
- tests/google/test_sheets_auth.py
execution_mode: code_change
owned_files:
- scripts/google/sheets_auth.py
- tests/google/test_sheets_auth.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before touching any code, load your implementer profile via the
`/ad-hoc-profile-load` skill (role: `implementer`, agent: `claude`). This applies
the mission's identity, governance scope, and boundaries for this session. Do not
proceed until the profile initialization declaration is complete.

## Branch Strategy

Current branch at workflow start: `feat/felix-time-logging`. Planning/base branch
for this feature: `feat/felix-time-logging`. Completed changes must merge into
`feat/felix-time-logging`. The concrete lane/worktree is resolved by
`/spec-kitty.implement` — do not create branches or worktrees by hand; let the
workflow place your commits.

## Objectives & Success Criteria

Deliver the **Sheets auth loader** — the credential layer for constraint **C-002**
(plan **IC-01**, contract **C3**). It returns `spreadsheets`-scoped Google
`Credentials` for a named account, reusing the #699 per-account OAuth substrate.

Success:

- `scripts/google/sheets_auth.py` exposes `load_sheets_credentials(account="personal")`
  returning valid Google `Credentials` whose granted scope covers
  `https://www.googleapis.com/auth/spreadsheets`.
- Per-account creds resolve under `~/.config/felix/google/<account>/`, honoring the
  `FELIX_GOOGLE_DIR` override.
- **Fail-safe**: on ANY auth problem (missing token, unreadable/invalid token, no
  `refresh_token`, refresh failure) the loader raises `SheetsAuthError` — it never
  returns broken credentials silently and never opens an interactive browser flow
  (office2 is headless).
- Tests green with branch coverage at the repo threshold.

## Context & Constraints

**Mirror `scripts/google/calendar_auth.py` EXACTLY in shape.** That module is the
proven, reviewed pattern; this WP is its Sheets-scoped sibling. Read it in full
first and reproduce its structure: `FELIX_GOOGLE_DIR` resolution read at call time,
per-account directory + charset validation (block `../` traversal), atomic token
write (temp + `os.replace`, dir `0700` / file `0600`), lazy `google.*` imports
inside the function (the packages live only in the office2 venv — importing this
module must stay CI-safe), and the load/refresh/fail-safe control flow.

Key differences from `calendar_auth.py`:

- **Least-privilege scope** is `https://www.googleapis.com/auth/spreadsheets`
  (not `calendar.events`). Provide `SCOPES_DEFAULT = ["https://www.googleapis.com/auth/spreadsheets"]`.
- The error type is **`SheetsAuthError`** — a distinct exception class from the
  calendar helper's `CalendarAuthError`.
- The public entrypoint is **`load_sheets_credentials(account="personal")`**.

**Load WITHOUT forcing scopes** (deploy gotcha #3, contract C3). Load the token
with its OWN granted scopes via `Credentials.from_authorized_user_file(str(tok))`.
Do NOT pass `scopes=` into the loader or refresh — forcing a scope that differs
from what the token was minted with makes the refresh fail `invalid_scope`. The
`personal` token is re-minted ONCE (out of band, at deploy — IC-05) with the
combined `calendar + spreadsheets` scopes; because this loader is scope-agnostic
at runtime, that combined token loads cleanly here AND keeps working for the
calendar helper. `SCOPES_DEFAULT` is advisory only — used in the re-mint hint
message, never forced at load/refresh.

`SheetsAuthError` messages must be actionable ("re-mint token on the Mac for
account `<x>` with scope `<spreadsheets>` …") — never print or return token
contents.

## Subtasks & Detailed Guidance

### T001 — `scripts/google/sheets_auth.py`

Author the loader module. Study `scripts/google/calendar_auth.py` and match its
structure member-for-member, adapting names/scope:

- Module docstring explaining the Sheets-scoped, per-account, fail-safe design and
  the load-without-forcing-scope rule (cite deploy gotcha #3).
- `SCOPES_DEFAULT = ["https://www.googleapis.com/auth/spreadsheets"]`.
- `DEFAULT_ACCOUNT = "personal"`; account charset validation identical to the
  calendar module (anchored regex, no path separators, no leading dot).
- `_google_dir()` reading `FELIX_GOOGLE_DIR` at call time; `credential_dir` /
  `client_secret_path` / `token_path` helpers per-account.
- Atomic `_write_token` (temp + `os.replace`, dir `0700`, file `0600`).
- `class SheetsAuthError(Exception)` with an actionable re-mint message contract.
- `load_sheets_credentials(account="personal", scopes=None) -> Credentials`:
  - lazy-import `google.auth.transport.requests.Request` and
    `google.oauth2.credentials.Credentials` inside the function (wrap `ImportError`
    into `SheetsAuthError` pointing at the office2 venv);
  - missing `token.json` → `SheetsAuthError`;
  - unreadable/invalid token (`OSError`/`ValueError`) → `SheetsAuthError`;
  - `creds.valid` → return unchanged;
  - `creds.expired and creds.refresh_token` → refresh in place (any refresh
    exception → `SheetsAuthError`), persist atomically, return;
  - otherwise (no refresh token / unusable) → `SheetsAuthError`.
  - Load with the token's OWN granted scopes — do NOT force `scopes`.

Keep `__all__` explicit (mirror the calendar module's export list, renamed).

### T002 — `tests/google/__init__.py` + `tests/google/test_sheets_auth.py`

- `tests/google/__init__.py` — package marker. **NOTE:** this file may already
  exist (empty) in the tree; if so, leave it as-is / ensure it remains present.
  Do not add content beyond what a package marker needs.
- `tests/google/test_sheets_auth.py` — mirror `tests/google/test_calendar_auth.py`.
  Inject fake `google.*` libraries into `sys.modules` **before** importing the SUT
  (the real packages are absent in CI); the module's lazy imports resolve the
  fakes at call time. Mock the google `Credentials` at the boundary
  (`from_authorized_user_file` monkeypatched per test). Cover:
  - **valid creds load** → returned unchanged (no refresh);
  - **missing token** → `SheetsAuthError` (actionable re-mint message);
  - **malformed/unreadable token** (`from_authorized_user_file` raises
    `OSError`/`ValueError`) → `SheetsAuthError`;
  - **`FELIX_GOOGLE_DIR` honored** — `credential_dir`/`token_path` resolve under the
    overridden root (use `monkeypatch.setenv` + a tmp dir);
  - (recommended, to keep branch coverage at threshold) expired-but-refreshable →
    refresh called + token persisted; refresh failure → `SheetsAuthError`; bad
    account name → `ValueError`; persisted perms `0600` / dir `0700`.

## Test Strategy

Run:

```
python3 -m pytest tests/google/test_sheets_auth.py -v --cov=scripts/google --cov-branch
```

Coverage of `scripts/google/sheets_auth.py` must meet the repo threshold. No test
touches the network or requires the real `google-*` packages — everything is
faked/mocked at the boundary, exactly as `test_calendar_auth.py` does.

## Definition of Done

- `load_sheets_credentials` returns `spreadsheets`-scoped `Credentials` for a named
  account, honoring `FELIX_GOOGLE_DIR`.
- Fail-safe on every auth failure path → `SheetsAuthError`, never a silent broken
  credential, never an interactive flow.
- Loads WITHOUT forcing scopes (uses the token's granted scope).
- `tests/google/test_sheets_auth.py` green; branch coverage at threshold;
  `tests/google/__init__.py` present.
- Module mirrors `calendar_auth.py` in shape (atomic write, lazy imports, charset
  validation, `__all__`).

## Risks

- **Forcing a scope on refresh → `invalid_scope`.** Must load/refresh with the
  token's granted scopes only; `SCOPES_DEFAULT` is advisory (re-mint hint) and must
  never be passed into `from_authorized_user_file` or the refresh call.
- **Combined `calendar + spreadsheets` token.** The `personal` token is re-minted
  once with both scopes (IC-05). Because both this loader and the calendar loader
  read the token scope-agnostically, the combined token must load cleanly in both —
  do not narrow or re-force scope in either module.
- **CI-safety.** `google-*` packages are not in `requirements.txt`; any non-lazy
  top-level google import would break CI. Keep imports inside the function.

## Reviewer Guidance

- Verify the loader **never forces scope** on load or refresh (no `scopes=` passed
  to `from_authorized_user_file`/refresh); confirm the re-mint hint uses
  `SCOPES_DEFAULT` as advisory text only.
- Verify **fail-safe**: every failure path raises `SheetsAuthError`; no path returns
  broken/`None` credentials; no interactive/browser flow is ever invoked.
- Verify the module **mirrors `calendar_auth.py`** in structure: atomic token write
  (`0700`/`0600`), lazy google imports, account charset validation, `FELIX_GOOGLE_DIR`
  read at call time, explicit `__all__`.
- Confirm `SheetsAuthError` is a distinct class (not reused from the calendar module)
  and least-privilege scope is `spreadsheets`.
- Confirm tests fake `google.*` at the boundary (no real packages, no network) and
  cover valid-load / missing-token / malformed-token / `FELIX_GOOGLE_DIR`.

## Activity Log

- 2026-07-11T01:14:23Z – claude:sonnet:python-pedro:implementer – shell_pid=40758 – Assigned agent via action command
- 2026-07-11T01:17:37Z – claude:sonnet:python-pedro:implementer – shell_pid=40758 – sheets_auth per-account/spreadsheets-scope, fail-safe, mirrors calendar_auth; 29 tests/100% cov; ruff clean; commit 9db3e7b4.
- 2026-07-11T01:17:42Z – claude:opus:reviewer-renata:reviewer – shell_pid=41877 – Started review via action command
- 2026-07-11T01:20:01Z – user – shell_pid=41877 – Review passed: mirror of calendar_auth.py; fail-safe verified (no forced scopes=); 29 tests 100% cov; mutation-tested non-synthetic; diff = 2 owned files only.

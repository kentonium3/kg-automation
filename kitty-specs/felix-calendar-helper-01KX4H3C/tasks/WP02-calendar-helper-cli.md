---
work_package_id: WP02
title: Calendar helper CLI — create/list/update/delete + self-check
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
- FR-007
- NFR-001
- NFR-003
- NFR-005
tracker_refs: []
planning_base_branch: feat/felix-calendar-helper
merge_target_branch: feat/felix-calendar-helper
branch_strategy: Planning artifacts for this mission were generated on feat/felix-calendar-helper. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-calendar-helper unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
- T008
agent: "claude:opus:python-pedro:implementer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/google/calendar_helper.py
create_intent:
- scripts/google/calendar_helper.py
- tests/google/test_calendar_helper.py
execution_mode: code_change
mission_id: 01KX4H3C4CZ2W0DRSHZHSNAY53
mission_slug: felix-calendar-helper-01KX4H3C
owned_files:
- scripts/google/calendar_helper.py
- tests/google/test_calendar_helper.py
role: implementer
tags: []
shell_pid: "51610"
---

# WP02 — Calendar helper CLI (CRUD + self-check)

## ⚡ Do This First: Load Agent Profile

Load `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Branch Strategy

- **Planning/base branch**: `feat/felix-calendar-helper` · **Merge target**: `feat/felix-calendar-helper`.
- Execution workspace resolved by `/spec-kitty.implement`. Contradictions → stop and resolve.

## Objective

Implement `scripts/google/calendar_helper.py` — the deterministic CLI that
authenticates (via WP01's `calendar_auth`) and performs event
create/list/update/delete plus a deploy `--self-check`, exactly per
**`../contracts/calendar-helper-cli.md`** (authoritative for flags, exit codes,
SUMMARY/JSON ordering) and **`../data-model.md`** (event body mapping, idempotency
key, attendee policy). Follow `docs/design/helper-script-conventions.md`.

Invocation (office2): `<venv>/bin/python -m scripts.google.calendar_helper …` with
cwd at the checkout (see quickstart). Locally it is `python3 -m …` inside a venv
with the google libs.

## Subtasks

### T004 — CLI shell, exit-code contract, service build
- argparse with subcommands `create` / `list` / `update` / `delete` and a top-level
  `--self-check` mode; common flags `--account` (default `personal`),
  `--calendar-id` (default `primary`), `--json`, `--dry-run`.
- Exit-code map (contract): `0` success · `1` operational/API/`not_found` · `2` usage/
  invalid account/bad input mode · `3` auth failure. Catch `CalendarAuthError` → exit 3
  with `ERROR: auth_failed …` on stderr and `SUMMARY: … status=auth_failed`; **never mutate on auth failure**.
- Build the Google service: `build("calendar","v3", credentials=load_credentials(account, SCOPES_DEFAULT), cache_discovery=False)`.
- Output ordering: `--json` object on a **preceding** stdout line; the **final** line is always `SUMMARY: …`.

### T005 — `create`
- Two input modes (mutually exclusive; both/neither → exit 2): `--payload-file <create_calendar_event envelope>`
  OR explicit flags `--summary/--start/--end/--start-timezone/--location/--description/--rrule/--attendees`.
- Map envelope→Google event body per data-model (summary, start/end `{dateTime,timeZone}`, location,
  description, `recurrence:[rrule]`, attendees `[{email}]`).
- `--send-updates {none,externalOnly,all}` default `none`. On the payload-file (inbox) path,
  **reject attendees unless `--allow-attendees`** (exit 2) — no silent external invites.
- Idempotency: `--idempotency-key` (inbox derives from `source_inbox_path`) → stamp
  `extendedProperties.private.felix_source_key`; before inserting, `events().list` a bounded
  window filtered by that private key and, on a match, **return the existing event**
  (`status=created idempotent=true`) instead of inserting.
- Success `SUMMARY: op=create status=created idempotent=<bool> event_id=<id> account=<a> calendar=<c>` (+ JSON `{status,event_id,html_link,idempotent}`).

### T006 — `list` / `update` / `delete`
- `list --from --to [--max 50]`: `events().list` in the window; emit concrete schema
  `{status:ok,count,events:[{event_id,summary,start,end,recurring}]}`; empty window = `count=0` (not an error).
- `update --event-id <id>` + fields: get-then-patch — only provided fields change; `--clear <comma-list>`
  removes optional fields. Recurring: operate on the id as given; a single-occurrence request →
  `ERROR: recurrence_scope_unsupported`, exit 2. Missing id → `ERROR: not_found`, exit 1.
- `delete --event-id <id> [--send-updates {none,all}]` (default none). Missing id → not_found/exit 1.

### T007 — `--self-check`
- Load creds, force a refresh, then a **bounded** `events().list(calendarId=primary, maxResults=1)`
  (covered by `calendar.events` — no calendars-list, no scope trap).
- Success `SUMMARY: op=self-check status=ok account=<a>`, exit 0. Any auth/scope/refresh failure → exit 3
  with the actionable re-mint message. **Never** interactive.

### T008 — Tests (`tests/google/test_calendar_helper.py`)
**CI-safe imports (important)**: google libs are NOT in `requirements.txt` (venv-only
on office2), so CI lacks them. Import google lazily in the module and inject fake
google modules via `sys.modules` in tests before importing the helper — the unit
tests must pass with **no** google packages installed. (The one `live_smoke` test
needs real libs and stays CI-skipped.)
Mock `googleapiclient.discovery.build` to return a fake `service` whose
`.events()` records insert/list/get/update/delete calls; mock `calendar_auth.load_credentials`
(valid + raising `CalendarAuthError`). Any unmocked `.execute()` must raise. Cover:
- create happy path (payload-file + explicit); event-body mapping incl. rrule/attendees;
- `sendUpdates=none` default (assert the kwarg); attendees rejected on payload-file path without `--allow-attendees`;
- idempotent retry (matching key → existing event, no second insert);
- list (window + empty); update patch + `--clear`; recurring-scope error; delete; not_found;
- `--self-check` ok + auth-fail (exit 3, no mutation);
- exit-code contract per subcommand; `SUMMARY:` is the final stdout line in every mode.

## Definition of Done
- [ ] All four subcommands + `--self-check` implemented per the contract; exit codes exact.
- [ ] Auth failure never mutates and always exits 3; no secrets in stdout/stderr.
- [ ] `pytest tests/google/test_calendar_helper.py --cov=scripts.google.calendar_helper --cov-branch` passes at/above threshold; no network (fake service).
- [ ] `SUMMARY:` is always the final stdout line; `--json` precedes it.

## Risks / reviewer guidance
- Verify idempotency actually prevents a duplicate on retry (the insert-succeeds/mark-fails window).
- Verify no live network in tests (fake service; `.execute()` guarded).
- Confirm timezone handling: RFC3339 offset + optional `--start-timezone` for recurrence correctness.
- Confirm attendee suppression default and the inbox-path attendee block.

## Activity Log

- 2026-07-09T23:41:28Z – claude:opus:python-pedro:implementer – shell_pid=51610 – Assigned agent via action command
- 2026-07-09T23:49:22Z – claude:opus:python-pedro:implementer – shell_pid=51610 – Ready for review — helper CLI + tests green (no network), exit-code contract + idempotency + fail-safe covered. Lint exit 0.

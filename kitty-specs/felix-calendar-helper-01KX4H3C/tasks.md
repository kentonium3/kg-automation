# Tasks: Felix Calendar Helper

**Mission**: felix-calendar-helper-01KX4H3C
**Branch**: `feat/felix-calendar-helper` (planning + all WP merges) → later `feat → main`
**Design docs**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)

Tests are in scope (NFR-003 requires them). Work packages are sized 3–5 subtasks.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Per-account credential path resolution + charset guard + perms | WP01 | | [D] |
| T002 | Load / refresh / persist creds; typed AuthError fail-safe (no headless consent) | WP01 | | [D] |
| T003 | Auth tests (valid / expired-refreshable / invalid_grant / account paths) | WP01 | | [D] |
| T004 | Helper CLI shell: subcommands, common flags, exit-code map, SUMMARY/JSON ordering, service build | WP02 | | [D] |
| T005 | `create`: payload-file + explicit; sendUpdates=none; `--allow-attendees`; idempotency key + dedupe | WP02 | | [D] |
| T006 | `list` / `update` / `delete`: window schema, patch + `--clear`, recurring-scope error, not_found | WP02 | | [D] |
| T007 | `--self-check`: refresh + bounded events.list; exit 3 with re-mint message | WP02 | | [D] |
| T008 | Helper tests: mock google client + Credentials; CRUD, idempotent retry, sendUpdates, exit codes, auth-fail | WP02 | | [D] |
| T009 | `route_calendar_event.py`: add `--create` mode (validate→build→invoke helper→emit status); DEFAULT_ACCOUNT→personal | WP03 | | [D] |
| T010 | `validate_calendar_event.py`: DEFAULT_ACCOUNT→personal (+ fixtures) | WP03 | | [D] |
| T011 | `felix-admin-calendar` AGENTS.md + TOOLS.md: judgment-only, helper not gog, keep clarification handling | WP03 | | [D] |
| T012 | `felix-admin-capture` AGENTS.md + .tmpl: calendar step = single `--create` command, no agent hop | WP03 | | [D] |
| T013 | Update inbox + calendar_routing tests for new default + `--create` mode | WP03 | | [D] |
| T014 | `deploys/queued/felix-calendar-helper.yaml` (Tier 3, audited_surface, pre/post verify) | WP04 | | [D] |
| T015 | `deploy-felix-calendar-helper.py`: Restic gate → uv venv provision → creds-presence → self-check | WP04 | | [D] |
| T016 | Deploy-script tests (mock subprocess/uv; gate ordering; idempotency) | WP04 | | [D] |
| T017 | `credential-manifest.json`: add personal Google OAuth credential | WP05 | [D] |
| T018 | `data-flows.json` + views: calendar now helper→Google (not gog); inbox→calendar inline | WP05 | [D] |
| T019 | `service-inventory.json` + md: external Calendar API dependency + on-demand helper (venv) | WP05 | [D] |
| T020 | `INDEX.md` + capability-roadmap status (#681/#699/#679) + new calendar-helper ops runbook | WP05 | [D] |

---

## WP01 — Calendar auth module (per-account, fail-safe)

- **Goal**: A reusable, unit-testable auth module that resolves per-account credentials and returns valid Google `Credentials`, failing safe on any auth error. Foundation for the helper.
- **Priority**: P1 (foundation) · **Depends on**: none
- **Independent test**: `pytest tests/google/test_calendar_auth.py` passes with the Google `Credentials`/refresh mocked; no network.
- **Subtasks**: T001, T002, T003
- **Requirements**: FR-005, FR-006, NFR-002, NFR-004
- **Prompt**: [tasks/WP01-calendar-auth.md](./tasks/WP01-calendar-auth.md) (~180 lines)

## WP02 — Calendar helper CLI (create/list/update/delete + self-check)

- **Goal**: The deterministic CLI that performs event CRUD + a deploy self-check against Google Calendar, per `contracts/calendar-helper-cli.md`.
- **Priority**: P1 (core) · **Depends on**: WP01
- **Independent test**: `pytest tests/google/test_calendar_helper.py` passes with the google client mocked; all subcommands + auth-fail path + idempotent-retry covered.
- **Subtasks**: T004, T005, T006, T007, T008
- **Requirements**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-007, NFR-001, NFR-003, NFR-005
- **Prompt**: [tasks/WP02-calendar-helper-cli.md](./tasks/WP02-calendar-helper-cli.md) (~300 lines)

## WP03 — Inbox rewire + felix-admin-calendar reshape (closes #679)

- **Goal**: Capture reaches the calendar via one deterministic `route_calendar_event --create` command (no agent hop); the calendar agent becomes judgment-only and calls the helper; default account → personal.
- **Priority**: P1 · **Depends on**: WP02
- **Independent test**: updated `tests/inbox` + `tests/calendar` pass; `--create` returns `created|needs_clarification|error`; no `gog`/`openclaw agent` on the calendar happy path (verified in prompts).
- **Subtasks**: T009, T010, T011, T012, T013
- **Requirements**: FR-008, FR-009
- **Prompt**: [tasks/WP03-inbox-rewire-agent-reshape.md](./tasks/WP03-inbox-rewire-agent-reshape.md) (~260 lines)

## WP04 — Deploy: manifest + deploy script

- **Goal**: Ship the helper to office2 safely — manifest + a deploy script that runs the Restic gate, provisions the uv venv (pinned), verifies staged creds, and runs the self-check smoke.
- **Priority**: P2 (deploy) · **Depends on**: WP02, WP03
- **Independent test**: `pytest tests/deploy/test_deploy_felix_calendar_helper.py` passes (subprocess/uv mocked); manifest validates against `deploys/schema/manifest-v1.schema.json`.
- **Subtasks**: T014, T015, T016
- **Requirements**: FR-010
- **Prompt**: [tasks/WP04-deploy.md](./tasks/WP04-deploy.md) (~230 lines)

## WP05 — Architecture documentation sync

- **Goal**: Keep the live architecture record faithful — new credential, changed calendar data-flow, service/dependency record, nav + roadmap + ops runbook.
- **Priority**: P2 · **Depends on**: none (parallel; finalized at merge)
- **Independent test**: `python tooling/scripts/validate_architecture_data.py` passes; Docs-CI green.
- **Subtasks**: T017, T018, T019, T020
- **Requirements**: FR-011
- **Prompt**: [tasks/WP05-architecture-docs.md](./tasks/WP05-architecture-docs.md) (~200 lines)

---

## Dependencies & sequencing

```
WP01 ──▶ WP02 ──▶ WP03 ──▶ WP04
                          ▲
                   (WP04 also deps WP02)
WP05  (independent, parallel)
```

- **MVP**: WP01 + WP02 (the helper itself, testable in isolation).
- **Closes #679**: WP03 (verified live at deploy per WP04 / quickstart SC-002).
- WP05 can run in parallel with WP01–WP04.

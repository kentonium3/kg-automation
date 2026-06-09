# Tasks: Capture Directive-6 Helpers Extraction

**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`
**Mission ID**: `01KTMS5QGXFJWQYVXB03SPYB48`
**Branch**: `kitty/mission-capture-d6-helpers-extraction-01KTMS5Q`
**Planning base / merge target**: `main`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-06-08

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | `mark_processed` tests + impl (idempotent + atomic frontmatter write) | WP01 | [P] |
| T002 | `mark_processed` coverage gate ≥90%/85% | WP01 | |
| T003 | `route_journal_entry` tests + impl (create-if-absent + append + heading) | WP02 | [P] |
| T004 | `route_journal_entry` coverage gate | WP02 | |
| T005 | `route_someday` tests + impl (Vikunja client + Someday project resolve + create) | WP03 | [P] |
| T006 | `route_someday` coverage gate | WP03 | |
| T007 | `route_calendar_event` tests + impl (validate via existing helper + emit normalized) | WP04 | [P] |
| T008 | `route_calendar_event` coverage gate | WP04 | |
| T009 | `handle_clarification_state` tests + impl (add / sweep / match subcommands + 24h aging) | WP05 | [P] |
| T010 | `handle_clarification_state` coverage gate | WP05 | |
| T011 | `classify_content` tests + impl (block split + per-block classification + ambiguous flagging) | WP06 | [P] |
| T012 | `classify_content` coverage gate | WP06 | |
| T013 | Extend `service-inventory.json` with 6 new component entries under felix-admin-capture | WP07 | |
| T014 | Bump `service-inventory.json` last_updated + extend updated_by | WP07 | |

`[P]` = WP-level parallelism — these WPs have no shared `owned_files` and can be implemented simultaneously via the Workflow tool.

## Work Packages

### WP01 — `mark_processed`

- **Goal**: Atomic frontmatter write helper. `python3 -m scripts.inbox.mark_processed --path <abs>` sets `status: processed` + `processed_at` atomically, preserving file location and other frontmatter fields. Idempotent.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_mark_processed.py --cov=scripts.inbox.mark_processed --cov-branch --cov-fail-under=90` passes.
- **Dependencies**: none
- **Estimated prompt size**: ~220 lines
- **Prompt file**: [tasks/WP01-mark-processed.md](./tasks/WP01-mark-processed.md)

Subtasks:
- [x] T001 `mark_processed` tests + impl (WP01) [P]
- [x] T002 `mark_processed` coverage gate ≥90%/85% (WP01)

---

### WP02 — `route_journal_entry`

- **Goal**: Append content to `08-Journal/Journal YYYY-MM-DD HHmm.md` (create if absent). Path from `scripts/vault/paths.json`.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_route_journal_entry.py --cov=scripts.inbox.route_journal_entry --cov-branch --cov-fail-under=90`.
- **Dependencies**: none
- **Estimated prompt size**: ~240 lines
- **Prompt file**: [tasks/WP02-route-journal-entry.md](./tasks/WP02-route-journal-entry.md)

Subtasks:
- [x] T003 `route_journal_entry` tests + impl (WP02) [P]
- [x] T004 `route_journal_entry` coverage gate (WP02)

---

### WP03 — `route_someday`

- **Goal**: Vikunja Someday-project task creation via the existing shared client. Resolve project by name, NOT hard-coded ID. Use create endpoint per C-006.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_route_someday.py --cov=scripts.inbox.route_someday --cov-branch --cov-fail-under=90`.
- **Dependencies**: none (consumes existing `scripts.common.vikunja_client.VikunjaClient`)
- **Estimated prompt size**: ~240 lines
- **Prompt file**: [tasks/WP03-route-someday.md](./tasks/WP03-route-someday.md)

Subtasks:
- [x] T005 `route_someday` tests + impl (WP03) [P]
- [x] T006 `route_someday` coverage gate (WP03)

---

### WP04 — `route_calendar_event`

- **Goal**: Validate calendar payload via existing `scripts.calendar_routing.validate_calendar_event`; emit normalized payload JSON on stdout; non-zero exit on invalid.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_route_calendar_event.py --cov=scripts.inbox.route_calendar_event --cov-branch --cov-fail-under=90`.
- **Dependencies**: none (consumes existing validator)
- **Estimated prompt size**: ~210 lines
- **Prompt file**: [tasks/WP04-route-calendar-event.md](./tasks/WP04-route-calendar-event.md)

Subtasks:
- [x] T007 `route_calendar_event` tests + impl (WP04) [P]
- [x] T008 `route_calendar_event` coverage gate (WP04)

---

### WP05 — `handle_clarification_state`

- **Goal**: Three subcommands (add / sweep / match) on `~/second-brain/agents/state/pending-calendar-clarifications.json`. 24h aging. Safe on missing state file.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_handle_clarification_state.py --cov=scripts.inbox.handle_clarification_state --cov-branch --cov-fail-under=90`.
- **Dependencies**: none
- **Estimated prompt size**: ~280 lines
- **Prompt file**: [tasks/WP05-handle-clarification-state.md](./tasks/WP05-handle-clarification-state.md)

Subtasks:
- [x] T009 `handle_clarification_state` tests + impl (WP05) [P]
- [x] T010 `handle_clarification_state` coverage gate (WP05)

---

### WP06 — `classify_content`

- **Goal**: Block-based deterministic content classification with LLM-judgment flagging for ambiguous tokens. Emit structured JSON.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_classify_content.py --cov=scripts.inbox.classify_content --cov-branch --cov-fail-under=90`.
- **Dependencies**: none
- **Estimated prompt size**: ~320 lines (most complex helper)
- **Prompt file**: [tasks/WP06-classify-content.md](./tasks/WP06-classify-content.md)

Subtasks:
- [x] T011 `classify_content` tests + impl (WP06) [P]
- [x] T012 `classify_content` coverage gate (WP06)

---

### WP07 — Architecture documentation sync (DIR-005)

- **Goal**: Extend `services[openclaw-gateway].agents.felix-admin-capture.components` array in `service-inventory.json` with 6 new component entries (one per helper). Bump `last_updated` + extend `updated_by`. Follow the existing component-entry schema verbatim.
- **Priority**: P2 (per DIR-005, docs ship with the feature)
- **Independent test**: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0.
- **Dependencies**: WP01, WP02, WP03, WP04, WP05, WP06 (docs accurately reflect what was built)
- **Estimated prompt size**: ~180 lines
- **Prompt file**: [tasks/WP07-architecture-docs.md](./tasks/WP07-architecture-docs.md)

Subtasks:
- [ ] T013 Extend `service-inventory.json` with 6 new component entries (WP07)
- [ ] T014 Bump `service-inventory.json` last_updated + extend updated_by (WP07)

---

## Parallelism Map

**WPs 1-6**: zero `owned_files` overlap. Each owns one helper + its test file:
- WP01: `scripts/inbox/mark_processed.py`, `tests/inbox/test_mark_processed.py`
- WP02: `scripts/inbox/route_journal_entry.py`, `tests/inbox/test_route_journal_entry.py`
- WP03: `scripts/inbox/route_someday.py`, `tests/inbox/test_route_someday.py`
- WP04: `scripts/inbox/route_calendar_event.py`, `tests/inbox/test_route_calendar_event.py`
- WP05: `scripts/inbox/handle_clarification_state.py`, `tests/inbox/test_handle_clarification_state.py`
- WP06: `scripts/inbox/classify_content.py`, `tests/inbox/test_classify_content.py`

These six can be implemented in PARALLEL via the Workflow tool. Each gets its own lane worktree off the coordination branch; each implementing agent writes its helper + tests independently; each runs `pytest --cov` to verify the gate; each commits + marks for_review independently.

**WP07** depends on WPs 1-6 and runs sequentially after.

## MVP Scope

WPs 1-6 form the deliverable surface. WP07 is doc-sync (mandatory per DIR-005). All 7 must land for the mission to ship.

## Test Strategy

Per **DIRECTIVE_034 Test-First**:
- Each implementation WP writes its test scaffold first, then the production helper.
- Each helper's coverage gate is enforced by its own pytest invocation (per-helper, not aggregate).
- Tests use `tmp_path` + `conftest.py` fixtures matching the existing `tests/inbox/` precedent.
- Vikunja client is mocked in WP03 tests (no real network).
- WP07 has no automated test beyond JSON validity (architecture-doc updates are reviewer-driven).

## Reviewer Guidance

- **WP01-06**: Focus on (a) atomic write correctness, (b) stdlib-only imports (no requests/httpx/pydantic), (c) `-m` invocation form in tests + docs, (d) exit-code contract honored, (e) coverage gate genuinely met (no `# pragma: no branch` abuse).
- **WP07**: JSON validates; new component entries match existing-entry schema.
- **Codex review**: per `[[project_next_mission_codex_review]]` and #330, AT LEAST ONE WP is reviewed via `--agent codex` (with `-p spec-kitty-review` profile + `sandbox_mode = "danger-full-access"` per `[[reference_codex_speckitty_profile]]`). WP01 (smallest surface) is the natural pick — small enough that any sandbox issue surfaces quickly.

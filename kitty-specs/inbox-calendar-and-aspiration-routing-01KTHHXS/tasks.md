# Tasks: Inbox calendar and aspiration routing

**Mission**: `inbox-calendar-and-aspiration-routing-01KTHHXS`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md) | **Data model**: [data-model.md](./data-model.md)

## Branch contract

- Planning/base branch: `main`
- Final merge target: `main`
- Current branch at tasks finalisation: `kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS` (the mission coord branch)
- `branch_matches_target: false` is reported by `check-prerequisites` because we are on the coord branch by necessity (3.2.0rc37 safe-commit refuses spec/plan/tasks commits on the protected `main` branch — see kg-automation#559 and Priivacy-ai/spec-kitty#1777). The mission still merges into `main` at `spec-kitty merge` time, sourcing the target from `meta.json`.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Scaffold `scripts/calendar/` module (dir + `__init__.py`) | WP01 |  |
| T002 | Implement `validate_calendar_event.py` per `contracts/validate_calendar_event.md` | WP01 |  |
| T003 | Validator unit tests + 11 fixtures | WP01 | [P] |
| T004 | Classifier regression fixture set (~25 cases incl. historical) | WP01 | [P] |
| T005 | Classifier regression test runner | WP01 | [P] |
| T006 | Pytest config + coverage thresholds (≥90% line, ≥85% branch on `scripts/calendar/`) | WP01 |  |
| T007 | Add Calendar event row to capture's Step 3 routing table + classifier prompt | WP02 |  |
| T008 | Add Aspiration/musing row + detection prompt | WP02 |  |
| T009 | Add Someday item row + Vikunja Someday project resolution + identity inference | WP02 |  |
| T010 | Tighten "Task or action item" rule | WP02 |  |
| T011 | Add completeness validation branch to capture (invoke `validate_calendar_event.py`) | WP02 |  |
| T012 | Capture writes PendingClarificationRecord JSONL on incomplete | WP02 |  |
| T013 | Capture: WhatsApp clarification prompt format + 24h timeout sweep | WP02 |  |
| T014 | Extend capture's `log_action` allowlist with new action types | WP02 |  |
| T015 | Felix main: "Calendar event creation (delegated)" section; shell out to `gog calendar create` | WP03 |  |
| T016 | Felix main: parse gog response; structured envelope JSON; log calendar_event_{created,failed} | WP03 |  |
| T017 | Felix main: "Calendar clarification reply handler" section; read pending-calendar-clarifications.jsonl on inbound | WP03 |  |
| T018 | Felix main: match reply to oldest open record; merge fields_so_far + reply; re-run validator | WP03 |  |
| T019 | Felix main: remove resolved record; flip source note to processed; log resolution | WP03 |  |
| T020 | Update `docs/design/architecture/data/service-inventory.json` (agent capabilities + gog new consumer) | WP04 | [P] |
| T021 | Update `docs/design/architecture/data/data-flows.json` (3 new flows) | WP04 | [P] |
| T022 | Update `docs/design/architecture/data-flows.md` narrative for the new flows | WP04 | [P] |
| T023 | Update `docs/design/architecture/data/signal-to-doc-map.json` doc_targets + verify INDEX/portal cross-refs | WP04 |  |

Total: 23 subtasks across 4 work packages.

## Work-package dependency graph

```
WP01 (helper + tests)  ←─ independent
WP04 (architecture docs) ←─ independent
WP02 (capture agent)  ←─ depends on WP01 (calls helper)
WP03 (Felix main)     ←─ depends on WP01, WP02 (extends state-file shape and delegation contract written by WP01/02)
```

WP01 and WP04 can run in parallel. WP02 starts when WP01 completes; WP03 starts when WP02 completes.

---

## WP01 — Calendar helper + validator tests + classifier regression set

**Goal**: Deliver the deterministic helper script `scripts/calendar/validate_calendar_event.py`, its unit-test fixture suite, and the broader inbox classifier regression fixture set + runner. Establishes the Directive 6 split-line for the mission: this WP is the deterministic surface; later WPs are the agent-prompt surface.

**Priority**: P1 — foundation. WP02 depends on this.

**Independent test**: `pytest tests/calendar/ tests/inbox/test_classifier_regression.py --cov=scripts/calendar --cov-branch --cov-fail-under=90` passes with all fixtures green and coverage thresholds met.

**Included subtasks**:

- [x] T001 Scaffold `scripts/calendar/` module (WP01)
- [x] T002 Implement `validate_calendar_event.py` (WP01)
- [x] T003 [P] Validator unit tests + fixtures (WP01)
- [x] T004 [P] Classifier regression fixture set (WP01)
- [x] T005 [P] Classifier regression test runner (WP01)
- [x] T006 Pytest config + coverage thresholds (WP01)

**Implementation sketch**:
1. Create the module + `__init__.py`.
2. Build `validate_calendar_event.py` implementing the stdin/stdout JSON contract from `contracts/validate_calendar_event.md`.
3. Write fixtures and tests in parallel with the helper to satisfy DIRECTIVE_034 (test-first).
4. Curate the classifier regression set from real historical inbox content (per memory `feedback_audit_judgment_scripts_for_bug_class` — grep `~/second-brain/agents/state/inbox-routing.jsonl` for historical misroutes if accessible, plus the documented examples from #324 and #556) — ~25 cases.
5. Write the regression runner that asserts expected classification destinations against the LLM prompt (out-of-scope to call live LLM here; runner asserts the prompt-input → expected-classification mapping; live LLM is exercised manually in quickstart smoke tests).
6. Wire pytest config + coverage thresholds in `pyproject.toml` or `pytest.ini` (whatever the repo already uses).

**Risks**: classifier regression runner approach (deterministic assertion vs. live LLM run) needs to balance reproducibility against fidelity to real classifier output. Address by making the runner extensible — fixtures carry both `input_block` and `expected_destination`; phase-1 runner reads the LLM prompt template and verifies the prompt would produce the expected destination via static analysis (rule extraction). If full static rule extraction is impractical, fall back to running against the actual LLM and accepting some non-determinism (use seed/temperature=0 patterns).

**Prompt file**: [tasks/WP01-calendar-helper-and-tests.md](./tasks/WP01-calendar-helper-and-tests.md)

---

## WP02 — Capture agent: routing rows, completeness, clarification, audit

**Goal**: Apply the four new/changed routing rows to `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`. Add the completeness validation branch that invokes the WP01 helper, the pending-clarifications state-file write, the WhatsApp clarification prompt format, the 24h timeout sweep, and the expanded `log_action` allowlist.

**Priority**: P1 — primary user-facing value (calendar routing + aspiration routing).

**Independent test**: capture agent processes the quickstart Test 1 (complete calendar event), Test 3 (aspiration → journal), Test 4 (Someday → Vikunja), Test 7 (tightened task rule), and Test 8 (negative regression on `attend X` task shape) successfully when manually triggered on office2 after deploy. Live LLM-driven; not a unit test.

**Included subtasks**:

- [x] T007 Add Calendar event row to Step 3 routing table (WP02)
- [x] T008 Add Aspiration/musing row (WP02)
- [x] T009 Add Someday item row + project resolution + identity inference (WP02)
- [x] T010 Tighten "Task or action item" rule (WP02)
- [x] T011 Add completeness validation branch (invoke validate helper) (WP02)
- [x] T012 Write PendingClarificationRecord JSONL on incomplete (WP02)
- [x] T013 WhatsApp clarification prompt format + 24h timeout sweep (WP02)
- [x] T014 Extend log_action allowlist (WP02)

**Implementation sketch**:
1. Edit the Step 3 table (lines ~199–222 of current AGENTS.md): replace the single "Task or action item" row with four rows in order: Calendar event → Aspiration/musing → Someday item → Active task. Add the rejection signals for "attend X" and "be Xer" patterns under the active-task row.
2. Add a new section "Calendar event completeness" that invokes `python3 /home/claude/kg-automation/scripts/calendar/validate_calendar_event.py < /tmp/calendar-block.json` and branches on `complete`.
3. Add a "Pending calendar clarifications" section explaining the JSONL state file shape (per `contracts/pending_clarification_record.md`) and the atomic-write helper invocation.
4. Add WhatsApp turn-summary formatting rules: when ≥1 incomplete calendar events were detected, the summary enumerates each missing-field set.
5. Add a "24h timeout sweep" sub-step in Step 1 (pre-scan branch): after prescan, also read the pending-clarifications file and timeout any records with `sent_at` >24h old.
6. Extend the Action Types table (lines ~550–580 of current AGENTS.md) with the new types: `calendar_event_created`, `calendar_event_failed`, `calendar_event_clarification_sent`, `calendar_event_clarification_resolved`, `calendar_event_clarification_timeout`, `journal_entry_appended`, `someday_task_created`.

**Risks**: classifier prompt size growing too long — Capture is Haiku-haiku per its identity label; prompt budget is constrained. Mitigation: keep new rows terse; defer detailed examples to memory or skill files where possible; verify post-edit AGENTS.md `wc -l` stays within current envelope.

**Prompt file**: [tasks/WP02-capture-agent-updates.md](./tasks/WP02-capture-agent-updates.md)

---

## WP03 — Felix main: calendar create + clarification reply handler

**Goal**: Update `scripts/openclaw/agents/main/AGENTS.md` (Felix main's tracked standing orders) to (a) accept calendar-creation delegation payloads from capture and shell out to `gog calendar create`, (b) handle inbound WhatsApp replies that resolve pending calendar clarifications by reading the JSONL state file, re-running the validator, and dispatching the completed event.

**Priority**: P1 — closes the calendar-create loop end-to-end.

**Independent test**: Felix main correctly executes the quickstart Test 1 (manual delegation of a complete-event payload yields a Google Calendar event) and Test 5 (clarification reply resolves an open record + creates the event). Live; not a unit test.

**Included subtasks**:

- [x] T015 Add "Calendar event creation (delegated)" section (WP03)
- [x] T016 Felix main: parse gog response + log_action (WP03)
- [x] T017 Add "Calendar clarification reply handler" section (WP03)
- [x] T018 Felix main: match reply, merge fields, re-run validator (WP03)
- [x] T019 Felix main: remove resolved record, flip source note, log (WP03)

**Implementation sketch**:
1. Add a new top-level section to `scripts/openclaw/agents/main/AGENTS.md` titled "Calendar event creation (delegated from capture)". Document the openclaw-agent inbound payload shape (matches `contracts/capture_to_main_calendar_payload.md`) and the gog command synthesis rules.
2. Add a sibling section "Calendar clarification reply handler" with the inbound-message flow: read JSONL, match record, merge fields, re-run validator, dispatch.
3. Document the `log_action` calls Felix main makes: `calendar_event_created`, `calendar_event_failed`, `calendar_event_clarification_resolved`.
4. Verify the new sections don't collide with existing Felix main responsibilities (calendar scheduling on direct WhatsApp request, etc.).

**Risks**: `openclaw doctor` warns Felix main's `message` tool is missing — channel-action calls like `thread-reply` can fail. Mitigation: this mission doesn't use channel-action APIs; all communication is via the natural openclaw outbound at end-of-turn. If end-of-turn outbound also fails on the missing tool, that's a pre-existing config gap to escalate separately.

**Prompt file**: [tasks/WP03-felix-main-calendar-handlers.md](./tasks/WP03-felix-main-calendar-handlers.md)

---

## WP04 — Architecture JSON + narrative doc-sync

**Goal**: Update the architecture inventories in `docs/design/architecture/data/` (service-inventory.json, data-flows.json, signal-to-doc-map.json) + the narrative `docs/design/architecture/data-flows.md` to reflect the new capabilities and data flows. Per DIR-005 these updates land in the same merge as the code/prompt changes — not a follow-up issue.

**Priority**: P2 — required for merge but does not block functional behavior on office2.

**Independent test**: `python tooling/scripts/validate_docs.py` passes (existing doc validator); JSON files remain schema-valid; cross-references in `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` are accurate.

**Included subtasks**:

- [x] T020 [P] Update `docs/design/architecture/data/service-inventory.json` (WP04)
- [x] T021 [P] Update `docs/design/architecture/data/data-flows.json` (WP04)
- [x] T022 [P] Update `docs/design/architecture/data-flows.md` narrative (WP04)
- [x] T023 Update `docs/design/architecture/data/signal-to-doc-map.json` + verify INDEX/portal cross-refs (WP04)

**Implementation sketch** (corrected on 2026-06-07 after `finalize-tasks --validate-only` surfaced that `agent-inventory.json` and `agents.md` do not exist — agents are catalogued IN `service-inventory.json` and the canonical narrative is `data-flows.md`):
1. `service-inventory.json`: extend `felix-admin-capture`'s capabilities entries with the new classification destinations; extend `main`'s capabilities with the calendar-delegation and clarification-reply handlers; update gog's `used_by` to include capture (via main delegation).
2. `data-flows.json`: add three new flow entries — `inbox → capture → main → gog → Google Calendar`, `inbox → capture → WhatsApp clarification → Kent reply → main → gog → Google Calendar`, `inbox → capture → 08-Journal`.
3. `data-flows.md`: extend the narrative with a section describing the inbox classification routing surface (including the calendar create-vs-clarify branches and the aspiration → journal flow).
4. `signal-to-doc-map.json`: ensure `change_class: service-modified` and `change_class: data-flow-added-or-modified` entries enumerate the real doc targets touched by this mission.

**Risks**: doc-validator strictness — schema changes in any of these JSONs could regress validation. Mitigation: run validator early (within the WP, not deferred to review) and fix any schema drift before commit.

**Prompt file**: [tasks/WP04-architecture-docsync.md](./tasks/WP04-architecture-docsync.md)

---

## MVP scope recommendation

**WP01 + WP02 = MVP for "no more useless calendar Vikunja todos."** With those two, calendar events are detected and routed away from Vikunja Inbox — even before the calendar-create loop closes via WP03. WP01+WP02 also delivers aspiration → journal and Someday routing on day one. WP03 (Felix main close-the-loop) and WP04 (doc-sync) are required for the full feature but the value is incremental.

## Parallelization opportunities

- WP01 and WP04 are fully independent — schedule in parallel.
- Within WP01, T003 / T004 / T005 are `[P]` (different fixture file groups).
- Within WP04, T020 / T021 / T022 are `[P]` (different JSON files).
- WP02 must wait for WP01; WP03 must wait for WP02.

## Next suggested command

`/spec-kitty.implement` (after `spec-kitty agent mission finalize-tasks` commits the WPs).

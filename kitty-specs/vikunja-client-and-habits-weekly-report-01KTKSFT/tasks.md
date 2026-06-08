# Tasks: Vikunja client + habits weekly report

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT`
**Spec**: [spec.md](./spec.md) (revision 2) | **Plan**: [plan.md](./plan.md) (revision 2) | **Research**: [research.md](./research.md) | **Data model**: [data-model.md](./data-model.md)

## Branch contract

- Planning/base branch: `main`
- Final merge target: `main`
- Current branch: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` (mission coord; required per #559 workaround chain)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Scaffold `scripts/common/vikunja_client.py` module + exception hierarchy | WP01 |  |
| T002 | Implement `VikunjaClient` class (construction, http methods, URL composition, header attachment) | WP01 |  |
| T003 | Implement error mapping (HTTP status → typed exceptions) + redaction-safe `__str__` + opt-in verbose mode | WP01 |  |
| T004 | Curate test fixtures for client (8 mock-response scenarios per `contracts/vikunja_client.md`) | WP01 | [P] |
| T005 | Write client unit tests (construction, URL normalization, methods, error mapping, redaction) | WP01 |  |
| T006 | Pytest coverage gate (≥90% line, ≥85% branch on `scripts/common/vikunja_client.py`) | WP01 |  |
| T007 | Scaffold `scripts/habits/query_active_habits_weekly.py` module | WP02 |  |
| T008 | Implement `HabitClassifier` (classify_habit, parse_weekday_in_title, scheduled_days_for_window) per FR-004 | WP02 |  |
| T009 | Implement Vikunja query loop (paginate done=true, parse `done_at`, filter to windows, aggregate by title) | WP02 |  |
| T010 | Implement WeeklyHabitReport JSON shape + CLI args + exit codes per `contracts/query_active_habits_weekly.md` | WP02 |  |
| T011 | Implement log_action calls (`weekly_report_generated`, `weekly_report_failed`) per FR-013 | WP02 |  |
| T012 | Curate weekly-helper test fixtures (8 scenarios per `contracts/query_active_habits_weekly.md`) | WP02 | [P] |
| T013 | Write weekly-helper unit tests + coverage gate (≥90% line, ≥85% branch) | WP02 |  |
| T014 | Update `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — add output-discipline Hard Rules (FR-008) | WP03 |  |
| T015 | Update `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — add weekly-report procedure section + revise "out of scope" statement (FR-009) | WP03 |  |
| T016 | Audit + edit `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` — Hard Rules added (escalation IS user-facing per phase-0 R-006) | WP03 |  |
| T017 | Audit `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` — Hard Rules OR no-user-facing-WhatsApp annotation per WP03 verification | WP03 |  |
| T018 | Update `docs/design/architecture/data/service-inventory.json` — capability summaries + vikunja_client infrastructure | WP04 | [P] |
| T019 | Update `docs/design/architecture/data/data-flows.json` — new weekly-habit-report flow | WP04 | [P] |
| T020 | Update `docs/design/architecture/data-flows.md` — narrative for the new flow | WP04 | [P] |
| T021 | Update `docs/design/architecture/data/signal-to-doc-map.json` + verify INDEX/portal cross-refs | WP04 |  |

Total: 21 subtasks across 4 work packages.

## Work-package dependency graph

```
WP01 (Vikunja client)        ←─ independent (foundation)
WP04 (architecture docs)     ←─ independent (parallelizable with WP01)
WP02 (weekly helper)         ←─ depends on WP01 (uses the client)
WP03 (AGENTS.md edits)       ←─ depends on WP02 (references the helper invocation path)
```

WP01 and WP04 can run in parallel. WP02 starts when WP01 completes; WP03 starts when WP02 completes.

---

## WP01 — Shared Vikunja client + tests

**Goal**: Deliver `scripts/common/vikunja_client.py` — the shared HTTP wrapper for Vikunja API consumers. Encapsulates base URL resolution, token loading, request execution, timeout, and typed error semantics. Full unit test suite with ≥90% line / ≥85% branch coverage.

**Priority**: P1 — foundation. WP02 depends on this.

**Independent test**: `pytest tests/common/ --cov=scripts/common/vikunja_client --cov-branch --cov-fail-under=90` passes with all assertions green and coverage gate met.

**Included subtasks**:

- [x] T001 Scaffold module + exception hierarchy (WP01)
- [x] T002 Implement `VikunjaClient` class (WP01)
- [x] T003 Error mapping + redaction-safe `__str__` (WP01)
- [x] T004 [P] Curate test fixtures (WP01)
- [x] T005 Write unit tests (WP01)
- [x] T006 Pytest coverage gate (WP01)

**Implementation sketch**:
1. Create `scripts/common/vikunja_client.py` with exception classes at top + `VikunjaClient` class.
2. Implement constructor: read base URL via `get_vikunja_base_url()` (strip trailing slash), read token from `/data/services/openclaw/secrets/vikunja-api`, validate, store.
3. Implement `_request(method, path, params, json, timeout)` private method: compose URL, attach headers, execute `urllib.request.urlopen` with timeout, parse JSON response, map errors.
4. Implement public methods `get/post/put/delete` as thin wrappers over `_request`.
5. Implement error-class mapping per contracts/vikunja_client.md.
6. Curate fixtures in parallel with tests.
7. Wire coverage gate in `pyproject.toml` or per-test invocation per the existing `scripts/inbox/`/`scripts/calendar_routing/` precedent.

**Risks**: Vikunja's actual filter syntax behavior (per memory `reference_vikunja_filter_gotchas.md`) may surface 400-class responses that the client should map cleanly. Mitigation: T003's error mapping covers VikunjaBadRequestError; T004 includes a `mock_response_400` fixture.

**Prompt file**: [tasks/WP01-vikunja-client.md](./tasks/WP01-vikunja-client.md)

---

## WP02 — Weekly habit-report helper + tests

**Goal**: Deliver `scripts/habits/query_active_habits_weekly.py` — the deterministic helper that queries Vikunja's `done_at` history via the shared client, classifies habits, computes per-habit percentages, and emits the WeeklyHabitReport JSON. Replaces felix-admin-habits' LLM-improvised data path.

**Priority**: P1 — primary user-facing fix.

**Independent test**: `pytest tests/habits/test_query_active_habits_weekly.py --cov=scripts/habits/query_active_habits_weekly --cov-branch --cov-fail-under=90` passes with all 8 fixture scenarios green.

**Included subtasks**:

- [ ] T007 Scaffold module (WP02)
- [ ] T008 Implement HabitClassifier (WP02)
- [ ] T009 Vikunja query loop + done_at filtering + aggregation (WP02)
- [ ] T010 WeeklyHabitReport JSON + CLI + exit codes (WP02)
- [ ] T011 log_action calls (WP02)
- [ ] T012 [P] Curate test fixtures (WP02)
- [ ] T013 Unit tests + coverage gate (WP02)

**Implementation sketch**:
1. Create `scripts/habits/query_active_habits_weekly.py`. Stdlib only beyond the client.
2. Implement `parse_weekday_in_title()` regex match against `(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?` (case-insensitive). Returns set of ISO weekday names or None.
3. Implement `classify_habit()` per FR-004 rules.
4. Implement `scheduled_days_for_window()` per FR-004 rules.
5. Implement `query_completion_events(client, window_start, window_end)` — paginate `/projects/13/tasks?filter=done=true` until partial/empty; filter `done_at` to window; classify each; emit `HabitCompletion` instances.
6. Implement `aggregate(events)` — group by habit_title, count per window, compute percentages.
7. Implement `main()` — parse args, instantiate client, run queries for current + prior window, build report JSON, write to stdout, exit 0.
8. Add exception-handler wrappers per exit-code table.
9. Add log_action invocations on success and failure.
10. Fixtures + tests in parallel.

**Risks**: Vikunja's `done_at` date-range filter syntax is not yet confirmed (research.md OP-001). Plan-phase open item. Mitigation: T009 first probes with a date-unbounded `?filter=done=true` query and date-filters client-side; if Vikunja supports server-side filter, optimize later (out of mission scope to verify the exact syntax).

**Prompt file**: [tasks/WP02-weekly-helper.md](./tasks/WP02-weekly-helper.md)

---

## WP03 — felix-admin-habits AGENTS.md edits + sibling audit

**Goal**: Update felix-admin-habits' standing orders with output-discipline Hard Rules + the weekly-report procedure. Audit felix-admin-escalation (confirmed user-facing-WhatsApp per phase-0) and felix-admin-tasker; apply Hard Rules to siblings if needed or add a no-user-facing-WhatsApp annotation.

**Priority**: P1 — fixes the leaked-internal-reasoning bug + rewires the agent to use the new helper.

**Independent test**: post-deploy, the next weekly cron tick (`habits-weekly-report` Sunday 22:00) produces a WhatsApp message whose first character is `S` in `Sent by felix-admin-habits:sonnet`, with no preamble and percentages matching the helper's JSON output. Verified by smoke-testing per `quickstart.md` Test 5.

**Included subtasks**:

- [ ] T014 felix-admin-habits AGENTS.md — Hard Rules (WP03)
- [ ] T015 felix-admin-habits AGENTS.md — weekly-report procedure + revise "out of scope" (WP03)
- [ ] T016 felix-admin-escalation AGENTS.md — Hard Rules added (WP03)
- [ ] T017 felix-admin-tasker AGENTS.md — Hard Rules OR no-WhatsApp annotation (WP03)

**Implementation sketch**:
1. Read felix-admin-capture's existing Hard Rules (lines ~33–84 of `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`) as the canonical template.
2. T014: insert mirrored Hard Rules into felix-admin-habits' AGENTS.md. Adjust language per habits-specific delivery channel (`Sent by felix-admin-habits:<model>`).
3. T015: add a "Weekly report" section documenting the helper invocation at deploy path, JSON parsing, WhatsApp turn-summary rendering format per `contracts/weekly_report_payload.md`. Remove or revise the pre-existing "weekly reports out of scope" statement.
4. T016: read felix-admin-escalation's existing AGENTS.md; insert Hard Rules mirrored from habits (consistent phrasing). Verify the identity line convention is `Sent by felix-admin-escalation:<model>`.
5. T017: read felix-admin-tasker's existing AGENTS.md. If it has any cron-driven user-facing WhatsApp surface, add Hard Rules. If not, add a brief comment near the top: `# No user-facing WhatsApp emission expected from this agent; output discipline rules unnecessary.` Document the audit conclusion either way.

**Risks**: Sonnet's prompt budget may be impacted by the expanded AGENTS.md. Mitigation: keep Hard Rules section concise (mirror capture's terse pattern); the existing capture-AGENTS.md is ~950 lines on Sonnet/Haiku and works.

**Prompt file**: [tasks/WP03-agents-md-edits.md](./tasks/WP03-agents-md-edits.md)

---

## WP04 — Architecture doc-sync

**Goal**: Update the architecture inventories + narrative to reflect the new shared client, the new weekly-helper flow, and the updated agent capabilities. Per DIR-005 these land in the same merge — not a follow-up.

**Priority**: P2 — required for merge but does not block functional behavior on office2.

**Independent test**: `python tooling/scripts/validate_docs.py` passes; JSON files remain schema-valid; cross-references in INDEX / portal accurate.

**Included subtasks**:

- [ ] T018 [P] service-inventory.json (WP04)
- [ ] T019 [P] data-flows.json (WP04)
- [ ] T020 [P] data-flows.md narrative (WP04)
- [ ] T021 signal-to-doc-map.json + INDEX/portal verification (WP04)

**Implementation sketch**:
1. T018: read service-inventory.json. Extend felix-admin-habits entry with the new weekly-report capability backed by the new helper. Extend felix-admin-escalation + felix-admin-tasker entries with the output-discipline rules in place (or no-WhatsApp note). Add a new entry for the shared `vikunja_client` infrastructure.
2. T019: read data-flows.json. Add a new flow: `weekly cron → felix-admin-habits → query_active_habits_weekly.py → vikunja_client → Vikunja API (done_at history) → WhatsApp turn-summary`. Mirror the shape of the existing morning-check-in flow.
3. T020: extend `docs/design/architecture/data-flows.md` narrative to describe the new weekly-habit-report flow.
4. T021: verify `signal-to-doc-map.json` covers the change_classes for this mission (service-modified, data-flow-added-or-modified). Spot-check `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` cross-references.

**Risks**: schema strictness in validate_docs.py — small structural errors block the gate. Mitigation: run `validate_docs.py` after each subtask, not just at end.

**Prompt file**: [tasks/WP04-architecture-docsync.md](./tasks/WP04-architecture-docsync.md)

---

## MVP scope recommendation

**WP01 + WP02 = MVP for "deterministic weekly habit data."** With those, the helper exists and can be invoked manually for verification even before WP03 rewires the agent. WP03 closes the user-facing loop. WP04 ships the doc-sync.

## Parallelization opportunities

- WP01 and WP04 are independent — schedule in parallel.
- Within WP01, T004 is `[P]` (fixture authoring concurrent with implementation).
- Within WP02, T012 is `[P]` (same).
- Within WP04, T018/T019/T020 are `[P]` (different JSON/MD files).
- WP02 must wait for WP01; WP03 must wait for WP02.

## Next suggested command

`/spec-kitty.implement` (after `spec-kitty agent mission finalize-tasks` commits the WPs).

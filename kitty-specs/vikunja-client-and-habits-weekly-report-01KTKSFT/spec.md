# Vikunja client + habits weekly report

**Mission ID**: 01KTKSFTZ3HMJDS73FPREW38NY
**Mission slug**: vikunja-client-and-habits-weekly-report-01KTKSFT
**Mission type**: software-dev
**Target branch**: main
**Created**: 2026-06-08
**Revision**: 2 (post phase-0 live-probe findings; FR-007 dropped, data source changed, recurrence math revised)
**Source issues**: kentonium3/kg-automation#562 (umbrella), #542 (foundation), #561 (co-shipped output-discipline)

## Purpose

**TL;DR**: Make the weekly habit report trustworthy by replacing LLM improvisation with a deterministic helper that queries Vikunja's actual completion history via a new shared client, and add output-discipline Hard Rules so the agent stops leaking internal reasoning to WhatsApp.

**Context**: The 2026-06-08 weekly-cron-fired WhatsApp message from felix-admin-habits surfaced three independent bugs: (a) internal agent monologue leaked above the identity line; (b) the report included one-off non-habit tasks like "Upload cardiac lab history"; (c) per-habit percentages were wrong (seven habits at 100% for a week they weren't completed every day) and the prior-week baseline was uniformly 0%. The agent's own leaked monologue diagnosed the root cause: AGENTS.md says weekly reports are out of scope, no helper script exists, but the cron fires anyway — so the agent improvises data via LLM reasoning.

Phase-0 live probes (recorded in research.md) verified that Vikunja DOES expose per-task completion history via the `done_at` field — `?filter=done=true` returns historical completed tasks with their completion timestamps. The morning check-in path (which works correctly per #556) reads a local sync cache that holds current state only; the weekly path needs historical data, which Vikunja serves directly. Mission scope: build a shared Vikunja client (#542 foundation), build a deterministic weekly helper that uses the client to query done_at history and roll up per habit, and add output-discipline Hard Rules across felix-admin-habits + audit-sibling fixes (#561).

## Domain Language

- **Habit**: a task in Vikunja project 13 ("Habits"). Two patterns observed in the live data:
  - **Daily habit**: `repeat_after=86400` (24h). Examples: "Wake at 5:00 AM", "Meditate", "Read 30 min minimum". When marked done, Vikunja auto-creates the next instance.
  - **Weekday-in-title habit**: `repeat_after=0`, title contains a weekday name (e.g., "Strength training — Monday"). One task per occurrence, no auto-recurrence in Vikunja; Kent or some other process creates the next instance.
- **Check-in (completion event)**: a Vikunja task transitioning to `done=true`. Recorded by Vikunja with a `done_at` timestamp. The completion signal queried by the weekly helper.
- **Morning check-in**: the daily-cadence message felix-admin-habits sends each morning listing today's scheduled habits. Reads from the local sync cache (`/data/services/openclaw/state/sync/task-cache.json`) via `scripts/habits/query_active_habits_v2.py` per #556's `363685ea` fix. Works correctly; **this mission does NOT migrate it**.
- **Weekly report**: the weekly-cadence message felix-admin-habits sends summarizing the past 7 days' habit completion vs. the prior 7-day baseline. Currently broken (this mission's primary fix). Queries Vikunja directly for `done_at` history because the sync cache holds current state only, no history.
- **Shared Vikunja client**: the new `scripts/common/vikunja_client.py` module. Centralizes base URL composition, token loading, request execution, timeout, and error semantics for direct Vikunja API consumers. Its first consumer is the new weekly helper.
- **Scheduled days in window**: the count of days within a 7-day window when a habit was "expected" to be completed. Daily habits: 7. Weekday-in-title habits: 1 per matched weekday (e.g., "X — Monday" = 1 Monday in the window).
- **Output discipline**: the set of Hard Rules in agent standing orders that forbid preamble before the identity line, between-tool-calls narration, and internal reasoning leakage to the announce-channel WhatsApp delivery. Established in felix-admin-capture's AGENTS.md (lines ~33–84); this mission extends it to felix-admin-habits and audits felix-admin-escalation + felix-admin-tasker.

## User Scenarios & Testing

### Primary scenario — weekly cron tick produces trustworthy report

- **Actor**: weekly cron on office2 (Sunday 22:00 America/New_York, cron `0 22 * * 0`, verified in phase-0) → felix-admin-habits agent (sonnet) → WhatsApp announce channel → Kent
- **Trigger**: Sunday 10pm cron tick
- **Happy path**:
  1. Cron fires the agent with the weekly-report intent.
  2. Agent invokes `python3 /home/claude/kg-automation/scripts/habits/query_active_habits_weekly.py --window 7d`.
  3. Helper instantiates the shared `vikunja_client` and issues `GET /projects/13/tasks?filter=done=true` (or equivalent done_at-bounded query — exact filter syntax determined in plan-phase contract).
  4. Helper iterates returned tasks; filters to those with `done_at` within the current 7-day window (and a separate query for the prior 7-day window for baseline); rolls up by canonical title (treating "Strength training — Monday" and "Strength training — Wednesday" as separate habits, not a single rollup).
  5. Helper computes per-habit completion: `completion_events_in_window / scheduled_days_in_window * 100`. Scheduled-days math: 7 for daily-cadence habits, 1 per matched weekday for weekday-in-title habits.
  6. Helper emits JSON; agent renders to WhatsApp turn-summary starting with `Sent by felix-admin-habits:sonnet` (no preamble), one row per habit, current + prior-week percentages, overall footer.
  7. WhatsApp message body first character is `S` in `Sent by ...`.
- **Always-true rule**: a non-habit task NEVER appears (filter is project_id=13 + repeat_after>0 OR weekday-in-title pattern); the agent's internal reasoning NEVER appears in the message body; per-habit percentages reflect actual `done_at` events, never LLM estimates.

### Primary scenario — morning check-in unchanged

- **Actor**: morning cron → felix-admin-habits → WhatsApp → Kent
- **Trigger**: daily morning cron tick (11:05 UTC per phase-0)
- **Happy path**: agent invokes the existing `query_active_habits_v2.py` (UNCHANGED in this mission); helper reads sync cache and returns today's scheduled habits; agent renders the morning check-in.
- **Always-true rule**: behavior identical to before this mission. This mission does NOT migrate v2 — v2 doesn't use Vikunja API directly; it uses the sync cache.

### Primary scenario variant — Vikunja unreachable during weekly report

- **Actor**: weekly cron → agent → helper → Vikunja API (timeout / 5xx / network)
- **Trigger**: Vikunja down or unreachable at the moment the weekly cron fires
- **Happy path**:
  1. Helper's call to the shared client raises a typed `VikunjaHttpError` / `VikunjaServerError` / `VikunjaTimeoutError`.
  2. Agent catches the exception, surfaces it in the turn-summary: `Sent by felix-admin-habits:sonnet\n\nWeekly report unavailable: <error class + redaction-safe message>`
  3. Agent does NOT fabricate data; does NOT retry within the cron tick; does NOT silently skip.
- **Always-true rule**: when the deterministic source fails, the agent reports the failure deterministically; no hallucinated numbers.

### Primary scenario — output discipline at sibling agents

- **Actor**: felix-admin-escalation OR felix-admin-tasker agents during their respective cron-fired messages (escalation-daily cron exists per phase-0; tasker may or may not have its own cron — confirmed in plan phase)
- **Trigger**: agent's standing orders are audited as part of this mission's acceptance
- **Happy path**: each sibling AGENTS.md is grepped for the canonical Hard Rules phrase (mirrored from capture's lines ~33–84). If missing, the rules are added in the same mission. If a sibling agent doesn't emit user-facing WhatsApp, that's documented as an explicit comment in its standing orders.
- **Always-true rule**: after this mission, every felix-admin-* agent either has the Hard Rules or has an explicit "no user-facing WhatsApp" annotation.

### Edge cases

- **Habit completed multiple times in the window** (e.g., daily habit completed all 7 days): each `done_at` event in the window counts as one completion; daily habit at 7/7 = 100%.
- **Habit completed 0 times in the window**: 0%; included in report with empty bar.
- **Habit recently created (mid-window)**: completions still appear for the days they happened; baseline (prior 7 days) may be 0 (the habit didn't exist). Acceptable per `(was 0%)` semantics; documented in the row.
- **Weekday-in-title habit completed on the matching weekday**: 1/1 = 100%.
- **Weekday-in-title habit NOT completed in the window**: 0/1 = 0%.
- **Non-habit task in project 13** (rare, but possible): filtered out by the `repeat_after > 0 OR weekday-in-title match` predicate. Plan phase confirms the predicate doesn't miss any real habits or include any real non-habits.
- **Vikunja done_at API quirk**: phase-0 confirmed `?filter=done=true` returns tasks with `done_at` populated. Plan phase confirms the filter-by-date-range syntax (e.g., `&filter=done_at>=2026-06-01`) — Vikunja's filter expression language has gotchas per memory `reference_vikunja_filter_gotchas.md`.
- **Agent prompt budget overflow**: habits agent runs on sonnet; expanded AGENTS.md (Hard Rules + new weekly-report procedure) must stay within sonnet's prompt budget.

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | A shared Vikunja client module exists at `scripts/common/vikunja_client.py`. Encapsulates base URL composition (via `scripts/common/vikunja_config.get_vikunja_base_url()` with trailing-slash normalization), token loading from `/data/services/openclaw/secrets/vikunja-api`, HTTP request execution via standard library `urllib.request`, timeout policy (30s default, per-request override), and error-class mapping (401→VikunjaAuthError, 404→VikunjaNotFoundError, 400→VikunjaBadRequestError, 5xx→VikunjaServerError, timeout→VikunjaTimeoutError, other→VikunjaHttpError). Errors are redaction-safe by default — exception messages include the request path but NOT request body or response body. | Pending |
| FR-002 | Client has no global state. Instantiating two clients in the same process is isolated; mocking `urlopen` in one test does not bleed into another. | Pending |
| FR-003 | A new deterministic helper at `scripts/habits/query_active_habits_weekly.py` queries Vikunja via the shared client for project-13 tasks completed within a configurable window (default current 7 days + prior 7-day baseline). Helper instantiates `VikunjaClient`, issues filter queries to surface `done_at`-bounded results, rolls up by canonical title, and emits JSON on stdout with per-habit per-window completion counts and percentages. Standard library only beyond the client. | Pending |
| FR-004 | Per-habit completion percentage is computed as `completion_events_in_window / scheduled_days_in_window * 100`. Scheduled-days math: (a) for daily-cadence habits (`repeat_after == 86400`), scheduled_days = number of complete days in the window (7 for a full week); (b) for weekday-in-title habits (e.g., "Strength training — Monday"), scheduled_days = the number of matched-weekday occurrences in the window (1 per week per matched weekday — match the day-of-week filter pattern from `query_active_habits_v2.py` per mission #408); (c) for habits that match neither pattern (none currently observed in Kent's data, but flagged for plan phase to confirm), scheduled_days is determined by plan-phase rules — default to 7/week if uncertain. | Pending |
| FR-005 | Helper computes the prior-week baseline by running the same query against the prior 7-day window. Returns a non-zero baseline when the operator actually completed habits in the prior period. The uniform-zero pattern observed in the 2026-06-08 message is a regression class to test against explicitly. | Pending |
| FR-006 | Non-habit tasks NEVER appear in the helper output. Filter predicate: `project_id == 13 AND (repeat_after > 0 OR title matches weekday-in-title pattern)`. The "Upload cardiac lab history" class of one-off task is filtered out at the helper layer, not in the agent's render step. Tasks with `repeat_after == 0` AND title that does NOT contain a weekday name are excluded. | Pending |
| FR-007 | **DROPPED in revision 2.** The `query_active_habits_v2.py` helper reads from the local sync cache (`/data/services/openclaw/state/sync/task-cache.json` via `scripts.common.sync_cache`), NOT from Vikunja's API directly. There is no Vikunja API call to migrate. The new weekly helper IS the first consumer of the shared client; no migration required for the morning-check-in path. Documented here for audit trail. | Dropped |
| FR-008 | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` gains an output-discipline section mirroring capture's Hard Rules (capture lines ~33–84). The three Hard Rules forbid: (a) preamble before the identity line in any user-facing message; (b) between-tool-calls narration; (c) any text before `Sent by felix-admin-habits:<model>` in cron-fired announce messages. | Pending |
| FR-009 | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` documents the weekly-report procedure: invoke the helper at the deployed path, parse JSON, render to a WhatsApp turn-summary with deterministic format (identity header, one row per habit, current + prior-week percentages, overall footer). The pre-existing "weekly reports out of scope" statement is removed or revised to reflect the new in-scope reality. | Pending |
| FR-010 | `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` and `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (and their deployed counterparts on office2 — paths verified in plan phase, since phase-0 found the assumed paths empty) are audited for the same output-discipline gap. If a sibling agent emits user-facing WhatsApp (escalation does — `escalation-daily` cron at `0 12 * * *` per phase-0), the Hard Rules are added in this mission. If a sibling does not emit user-facing WhatsApp, an explicit comment to that effect is added to its standing orders. | Pending |
| FR-011 | Test coverage for the new client: ≥90% line and ≥85% branch on `scripts/common/vikunja_client.py`. Test coverage for the new weekly helper: ≥90% line and ≥85% branch on `scripts/habits/query_active_habits_weekly.py`. Both verified via `pytest --cov-branch --cov-fail-under=90`. | Pending |
| FR-012 | The new test surfaces include explicit regression tests for: (a) cardiac-task-class non-habit filtering (project 13 task with `repeat_after=0` and no weekday in title), (b) weekday-in-title percentage math (Mon habit completed once on Monday in window returns 100%), (c) prior-week baseline returns non-zero against historical fixture data, (d) Vikunja-unreachable produces typed exception, (e) base-URL trailing-slash normalization, (f) redaction-safe error messages. | Pending |
| FR-013 | Every classification decision and downstream action in the new helper logs via the existing `log_action.py` observability stream. New action types added: `weekly_report_generated`, `weekly_report_failed`. The agent's render step logs `weekly_report_sent` after the turn-summary is composed. | Pending |
| FR-014 | The weekly cron's invocation pattern is verified — DONE in phase-0: `habits-weekly-report` at `0 22 * * 0` Sunday 10pm America/New_York, `announce` delivery to WhatsApp. AGENTS.md's documented procedure matches this cadence. The pre-existing "out of scope" / cron-firing contradiction is resolved by updating AGENTS.md (this mission's approach). | Verified (phase-0); implementation pending |

## Non-Functional Requirements

| ID | Description | Measurable threshold | Status |
|---|---|---|---|
| NFR-001 | Weekly helper execution latency. | ≤5 seconds at the 95th percentile under normal Vikunja load on office2. Helper makes ≤4 API calls (current-window done query, prior-window done query, project listing if needed, task-detail lookups if any). | Pending |
| NFR-002 | No silent drops in the weekly report path. | 100% of weekly cron ticks either produce a complete report OR surface a `weekly_report_failed` action log AND a `Weekly report unavailable: <reason>` WhatsApp message. Zero ticks produce a hallucinated report. | Pending |
| NFR-003 | Audit trail completeness. | 100% of weekly cron ticks produce a structured log_action entry. Existing morning-check-in log behavior preserved. | Pending |
| NFR-004 | Idempotency. | Running the helper twice with the same `--window` argument and the same Vikunja state produces byte-identical JSON output. | Pending |
| NFR-005 | Client + helper test coverage. | ≥90% line, ≥85% branch on `scripts/common/vikunja_client.py` AND `scripts/habits/query_active_habits_weekly.py` per FR-011. | Pending |
| NFR-006 | Morning check-in zero-regression. | `query_active_habits_v2.py` and its tests remain UNTOUCHED in this mission. No code changes; no test changes. The morning-check-in path is verified to still work post-deploy via a smoke test (existing morning cron continues to produce its check-in). | Pending |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Standard library only for the new client and helper (no `requests`, no third-party HTTP libs). | Pending |
| C-002 | Reuse existing `log_action.py` observability stream. New action types extend the existing allowlist. | Pending |
| C-003 | Reuse existing `scripts/common/vikunja_config.py::get_vikunja_base_url()` for base URL resolution. Do not introduce a parallel URL helper. | Pending |
| C-004 | The morning check-in path (`query_active_habits_v2.py` + `sync_cache.py`) is NOT modified by this mission. The cache discipline established in #556's `363685ea` is preserved as-is. | Pending |
| C-005 | The absolute privacy rule applies: no read, write, reference, or log of `~/second-brain/notes/04-Growth/_private/` content. | Pending |
| C-006 | Change scope is Tier 3 (Logic / Workflow): client module, helper script, agent prompt edits, tests, architecture JSON updates. No host configuration, network, credential, port, or sudo-protected resource is modified. | Pending |
| C-007 | This mission introduces no new external services. The shared Vikunja client is new infrastructure code consuming existing Vikunja service + existing credential. | Pending |
| C-008 | #542's "two existing migrations" criterion is NOT honored in this mission (zero migrations occur — the new weekly helper is new code, not a migration). Documented as a deliberate scope correction post phase-0. The first existing-migration target (e.g., `scripts/sync/fetch.py`, which DOES consume Vikunja API to populate the cache) becomes a deliberate follow-up issue. | Pending |

## Success Criteria

- **SC-001 — Weekly report contains only habits**: in the 14 days following deployment, every weekly cron tick produces a report whose rows are all habits (`project_id == 13 AND (repeat_after > 0 OR weekday-in-title pattern)`). No one-off tasks appear.
- **SC-002 — Weekly report percentages match Vikunja data**: spot-check at least one cron tick by comparing the agent's reported percentage for one habit against Vikunja's actual `done_at` events for that habit over the same 7-day window. Match exactly.
- **SC-003 — Prior-week baseline reflects reality**: the same spot-check confirms the `(was X%)` annotation is the helper's actual prior-window done_at query result, not a uniform 0%.
- **SC-004 — Weekly report identity-line discipline**: in the 14 days following deployment, every weekly-cron WhatsApp message begins literally with `Sent by felix-admin-habits:<model>`. No preamble.
- **SC-005 — Sibling agents audited**: at deployment time, `scripts/openclaw/agents/felix-admin-{escalation,tasker}/AGENTS.md` (and their deployed counterparts) have been audited; rules added if missing OR explicit no-WhatsApp annotation present.
- **SC-006 — Client used by new weekly helper**: `scripts/habits/query_active_habits_weekly.py` imports from `scripts.common.vikunja_client` and the weekly cron's output reflects real Vikunja completion data.
- **SC-007 — Failure surfaces as failure, not hallucination**: if Vikunja is unreachable during a weekly cron tick (verifiable by deliberately blocking the office2 → vikunja path for a single tick), the WhatsApp message body says `Weekly report unavailable: <reason>` and a `weekly_report_failed` action is logged. No hallucinated data.
- **SC-008 — Morning check-in unchanged**: the morning cron continues to produce its check-in identical to pre-mission behavior. No regression in `query_active_habits_v2.py`'s output (it's untouched).

## Key Entities

- **VikunjaClient**: new class in `scripts/common/vikunja_client.py`. Stateless per-instance configuration (base URL, token, timeout). Methods: `get(path, **kwargs)`, `post(path, json=, **kwargs)`, `put`, `delete`. Returns parsed JSON or raises a typed exception.
- **VikunjaHttpError, VikunjaAuthError, VikunjaNotFoundError, VikunjaBadRequestError, VikunjaServerError, VikunjaTimeoutError**: exception hierarchy. All inherit from `VikunjaError` (base). All carry the request path; default-redacted bodies; opt-in verbose mode.
- **WeeklyHabitReport (JSON shape from the new helper)**: structured payload the agent consumes. Shape: `{"window_start_iso": ..., "window_end_iso": ..., "prior_window_start_iso": ..., "prior_window_end_iso": ..., "habits": [{"habit_title": str, "scheduled_days_current": int, "completed_events_current": int, "percent_current": float, "scheduled_days_prior": int, "completed_events_prior": int, "percent_prior": float, "habit_kind": "daily" | "weekday-in-title" | "other"}], "overall_percent_current": float, "overall_percent_prior": float}`. Helper computes everything; agent only renders.
- **HabitClassifier**: pure function in the new helper that takes a Vikunja task dict and returns the habit kind. Rules: `repeat_after == 86400 → "daily"`, `repeat_after == 0 AND title matches /(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?/i → "weekday-in-title"`, anything else → "other". Scheduled-days math is then derived per kind per FR-004.
- **Output discipline Hard Rules (text block)**: the three rules mirrored from capture's AGENTS.md.
- **log_action event types (existing, extended)**: new entries `weekly_report_generated`, `weekly_report_failed`, `weekly_report_sent`.

## Assumptions

- Vikunja's `?filter=done=true` query returns historical completed tasks with `done_at` populated, AND a date-range refinement is expressible (e.g., `&filter=done_at>=<iso>`). Phase-0 confirmed the basic done_at query; the date-range syntax is verified in plan-phase contract work.
- The day-of-week parsing rule for weekday-in-title habits matches Kent's actual title conventions ("Strength training — Monday", "Strength training — Wednesday", "Strength training — Friday" all observed). Other habits with weekday encoding in unexpected forms (e.g., abbreviated, in parentheses) would be misclassified; plan phase audits all 11 habits to confirm or extends the pattern.
- felix-admin-habits' agent runs on sonnet per the 2026-06-08 message header `Sent by felix-admin-habits:sonnet`.
- The sibling-agent audit will find felix-admin-escalation emitting user-facing WhatsApp (it has a daily cron per phase-0: `escalation-daily` at `0 12 * * *`); felix-admin-tasker is more ambiguous and confirmed in plan phase.
- "WP04 T015" cited in the leaked agent monologue is confabulation (no plausible prior mission's WP04 T015 referenced in the codebase). Documented as agent-hallucination evidence; not load-bearing.

## Documentation Synchronization Requirement

Per DIR-005 and the kg-automation change-control protocol, this mission's merge MUST include synchronized updates to the following docs:

- `docs/design/architecture/data/service-inventory.json` — felix-admin-habits capability summary (revised: weekly-report capability now backed by deterministic helper). felix-admin-escalation and felix-admin-tasker capability summaries updated per the audit. New entry or sub-note for the shared `vikunja_client` infrastructure.
- `docs/design/architecture/data/data-flows.json` — new flow: `weekly cron → felix-admin-habits → query_active_habits_weekly.py → vikunja_client → Vikunja API (done_at history) → WhatsApp turn-summary`.
- `docs/design/architecture/data-flows.md` — narrative description of the new weekly-habit-report flow.
- `docs/design/architecture/data/signal-to-doc-map.json` — verify `change_class: service-modified` and `change_class: data-flow-added-or-modified` `doc_targets` arrays cover the docs touched.
- `tests/common/` — unit tests for the new `vikunja_client.py`.
- `tests/habits/` — unit tests for the new weekly helper.

## Out of Scope

- Migration of any existing helper to the shared client (including `scripts/sync/fetch.py` which IS a Vikunja API consumer — that's the natural first migration target for a follow-up issue per #542's original "two existing migrations" criterion).
- Voice / UX changes to the weekly report beyond fixing the data quality.
- New habit-tracking features (streaks, missed-day detection, milestone alerts).
- Changes to the morning check-in path (`query_active_habits_v2.py`, `sync_cache.py`). Out of scope explicitly per C-004.
- Changes to the sync driver (`scripts/sync/`). Cache discipline preserved.
- Cron infrastructure changes beyond the AGENTS.md documenting the existing cron.
- The inbox-cleanup bug filed at #563.

## Cross-references

- **kentonium3/kg-automation#562** — source umbrella issue. This mission addresses #562 in full.
- **kentonium3/kg-automation#542** — foundation issue (shared Vikunja client). This mission ships the foundation; zero existing migrations occur (the new weekly helper is new code, not a migration). Follow-up issue tracks the first existing-migration target.
- **kentonium3/kg-automation#561** — co-shipped output-discipline issue.
- **kentonium3/kg-automation#556** — precedent: morning-check-in fix via `363685ea` (sync pagination + project 13 scope + sync cache discipline).
- **kentonium3/kg-automation#518** — sync cache mission (provides the cache `query_active_habits_v2.py` consumes).
- **kentonium3/kg-automation#408** — day-of-week filter mission (provides the weekday-in-title pattern this mission's weekly helper mirrors).
- **Felix Constitution Directive 6** — scripts-vs-LLM split.
- **Memory notes**: `reference_vikunja_recurrence_model.md` (recurrence model — note revised in light of phase-0 findings: most habits aren't repeat_after-encoded), `reference_vikunja_filter_gotchas.md` (filter syntax gotchas the client must navigate), `reference_vikunja_post_partial_replace.md`, `feedback_scripts_vs_llm.md`, `feedback_audit_judgment_scripts_for_bug_class.md`, `feedback_architecture_docs_first.md`.

## Spec-ready criteria

- [x] **Executive Summary** states what the feature delivers in 2-3 sentences
- [x] **Problem Statement** captures current vs target state concretely
- [x] **Study These Files First** lists internal pointers (via Cross-references)
- [x] **Functional Requirements** has at least one FR with success criteria; FR-007 explicitly DROPPED in revision 2 with audit trail
- [x] **Out of Scope** lists explicit exclusions
- [x] **Architecture Impact** identifies affected JSON files
- [x] **Constitutional Compliance** addressed throughout the FRs + Constraints
- [x] **Design-time discipline** — deterministic-vs-stochastic split called out: helper (deterministic) + agent rendering (stochastic, but constrained)

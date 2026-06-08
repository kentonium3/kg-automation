# Vikunja client + habits weekly report

**Mission ID**: 01KTKSFTZ3HMJDS73FPREW38NY
**Mission slug**: vikunja-client-and-habits-weekly-report-01KTKSFT
**Mission type**: software-dev
**Target branch**: main
**Created**: 2026-06-08
**Source issues**: kentonium3/kg-automation#562 (umbrella), #542 (foundation), #561 (co-shipped output-discipline)

## Purpose

**TL;DR**: Make the weekly habit report trustworthy by replacing LLM improvisation with a deterministic helper, building it on a shared Vikunja client that future scripts also use, and adding output-discipline Hard Rules so the agent stops leaking internal reasoning to WhatsApp.

**Context**: The 2026-06-08 weekly-cron-fired WhatsApp message from felix-admin-habits surfaced three independent bugs in a single output: (a) the agent's internal monologue (the agent self-debating whether the capability is in scope) leaked into the message body before the identity line; (b) the report included one-off non-habit tasks like "Upload cardiac lab history" in the per-habit completion table; (c) the per-habit percentages were wrong (seven habits at 100% for a week they weren't completed every day) and the prior-week baseline was uniformly 0% across the board. The agent's own leaked monologue diagnosed the root cause: there's no deterministic helper backing the weekly query, AGENTS.md says weekly reports are out of scope, but the cron fires anyway — so the agent improvises data via LLM reasoning. This mission delivers the bundled #562/#542/#561 slice: shared Vikunja client foundation, deterministic weekly-query helper plus migration of the existing morning-check-in query, and output-discipline Hard Rules across felix-admin-habits + audit-sibling fixes for felix-admin-escalation and felix-admin-tasker.

## Domain Language

- **Habit**: a task in Vikunja project 13 ("Habits") with `repeat_after > 0` (recurring on a cadence). Distinct from one-off tasks that happen to live in or near the same project.
- **Daily habit**: a habit with `repeat_after == 86400` (daily). Most habits Kent tracks.
- **Recurring-on-weekday habit**: a habit with `repeat_after == 604800` (weekly), scheduled on a specific weekday derived from the `due_date` field. Example: "Strength training — Wed" with due_date Wed and repeat_after 604800 is scheduled only on Wednesdays.
- **Check-in**: a task instance being marked `done` in Vikunja for a given day. The completion signal.
- **Morning check-in**: the daily-cadence message felix-admin-habits sends each morning listing today's scheduled habits. Currently works correctly via `scripts/habits/query_active_habits_v2.py` per #556's `363685ea` fix.
- **Weekly report**: the weekly-cadence message felix-admin-habits sends summarizing the past 7 days' habit completion vs. the prior 7-day baseline. Currently broken (this mission's primary fix).
- **Shared Vikunja client**: the new `scripts/common/vikunja_client.py` module that centralizes base URL composition, token loading, request execution, timeout, and error semantics. Replaces N copy-paste wrappers across `scripts/{sync,habits,escalation,enrichment,vikunja}/`.
- **Output discipline**: the set of Hard Rules in agent standing orders that forbid preamble before the identity line, between-tool-calls narration, and internal reasoning leakage to the announce-channel WhatsApp delivery. Established in felix-admin-capture's AGENTS.md (lines ~33–84); this mission extends it to felix-admin-habits, felix-admin-escalation, and felix-admin-tasker.

## User Scenarios & Testing

### Primary scenario — weekly cron tick produces trustworthy report

- **Actor**: weekly cron on office2 → felix-admin-habits agent (sonnet) → WhatsApp announce channel → Kent
- **Trigger**: weekly cron tick at the cadence configured on office2 (verified in plan phase via `openclaw cron list --json`)
- **Happy path**:
  1. Cron fires the agent with the weekly-report intent.
  2. Agent invokes `python3 /home/claude/kg-automation/scripts/habits/query_active_habits_weekly.py --window 7d`.
  3. Helper queries Vikunja via the shared `vikunja_client` for project 13 tasks, applies the same daily-habit + recurring-habit filter as `query_active_habits_v2.py`, computes per-habit per-day completion data for the current 7-day window AND the prior 7-day window, returns deterministic JSON.
  4. Agent renders the JSON to a WhatsApp turn-summary: identity header on first line (`Sent by felix-admin-habits:sonnet`), one row per habit with completion bars and percentages, accurate prior-week baselines with `(was X%)` annotations, an overall percentage footer.
  5. WhatsApp message body begins literally with `Sent by felix-admin-habits:sonnet` — no preamble, no internal reasoning, no between-tool-calls narration.
- **Always-true rule**: a calendar-classified or one-off Vikunja task (non-habit, e.g., "Upload cardiac lab history") NEVER appears in the weekly report; the agent's internal reasoning NEVER appears in the WhatsApp message body.

### Primary scenario — morning check-in unchanged

- **Actor**: morning cron → felix-admin-habits → WhatsApp → Kent
- **Trigger**: daily morning cron tick
- **Happy path**: agent invokes the migrated `query_active_habits_v2.py` (now using the shared `vikunja_client`); helper returns the same task list it did pre-migration; agent renders the morning check-in.
- **Always-true rule**: behavior identical to pre-migration. No regression in the morning-check-in output.

### Primary scenario variant — Vikunja unreachable during weekly report

- **Actor**: weekly cron → agent → helper → Vikunja API (timeout / 5xx / network)
- **Trigger**: Vikunja down or unreachable at the moment the cron fires
- **Happy path**:
  1. Helper raises a typed `VikunjaHttpError` / `VikunjaServerError` / `VikunjaTimeoutError` from the shared client.
  2. Agent catches the exception, surfaces it in the turn-summary: `Sent by felix-admin-habits:sonnet\n\nWeekly report unavailable: <error class + redaction-safe message>`
  3. Agent does NOT fabricate data; does NOT retry within the cron tick; does NOT silently skip.
- **Always-true rule**: when the deterministic source fails, the agent reports the failure deterministically; no hallucinated numbers.

### Primary scenario — output discipline at sibling agents

- **Actor**: felix-admin-escalation OR felix-admin-tasker agents during their respective cron-fired messages
- **Trigger**: agent's standing orders are audited as part of this mission's acceptance
- **Happy path**: each sibling AGENTS.md is grepped for the canonical Hard Rules phrase (mirrored from capture's lines ~33–84). If missing, the rules are added in the same mission. If a sibling agent doesn't emit user-facing WhatsApp at all, that's documented as an explicit comment in its standing orders.
- **Always-true rule**: after this mission, every felix-admin-* agent either has the Hard Rules or has an explicit "no user-facing WhatsApp" annotation.

### Edge cases

- **Mid-week mission deploy**: weekly report runs the day after deploy; prior-week baseline points into the period before any of the new code existed. Helper still returns correct data from Vikunja's historical check-in records.
- **Habit with no check-ins**: e.g., assume some habit Kent skipped. Returns 0% for current and prior weeks; row included with `░░░░░░ 0% (was 0%) →` indicator.
- **Habit recently created (mid-week)**: helper either includes it with `(was —%)` or excludes it from the prior-week baseline (plan phase decides). Either is acceptable; spec defers the choice.
- **Weekly habit (Wed-only) completed on the one Wed**: returns 100% (1 of 1 scheduled day), NOT 14% (1 of 7 calendar days).
- **Weekly habit (Wed-only) NOT completed**: returns 0% (0 of 1 scheduled), with bar `░░░░░░`.
- **Vikunja `repeat_after == 0` (one-off task)**: helper filters out. Even if the task happens to live in project 13, no `repeat_after` means it's not a habit.
- **Agent prompt budget overflow**: habits agent runs on sonnet; expanded AGENTS.md (Hard Rules + new weekly-report procedure) must stay within sonnet's prompt budget. Plan phase checks line count and per-section length.

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | A shared Vikunja client module exists at `scripts/common/vikunja_client.py`. Encapsulates base URL composition (via `scripts/common/vikunja_config.get_vikunja_base_url()` with trailing-slash normalization), token loading from `/data/services/openclaw/secrets/vikunja-api`, HTTP request execution via standard library `urllib.request`, timeout policy (30s default, per-request override), and error-class mapping (401→VikunjaAuthError, 404→VikunjaNotFoundError, 400→VikunjaBadRequestError, 5xx→VikunjaServerError, timeout→VikunjaTimeoutError, other→VikunjaHttpError). Errors are redaction-safe by default — exception messages include the request path but NOT request body or response body. | Pending |
| FR-002 | Client has no global state. Instantiating two clients in the same process is isolated; mocking `urlopen` in one test does not bleed into another. | Pending |
| FR-003 | A new deterministic helper at `scripts/habits/query_active_habits_weekly.py` queries Vikunja via the shared client, applies the same project-13 + daily-habit + recurring-habit filter as `query_active_habits_v2.py`, computes per-habit per-day completion data for a configurable window (default current 7 days + prior 7-day baseline), and emits JSON on stdout. Standard library only beyond the client. | Pending |
| FR-004 | Helper computes per-habit completion percentage as `completed_scheduled_days / total_scheduled_days * 100` where `total_scheduled_days` respects each habit's `repeat_after` + `repeat_mode` + `due_date` (per memory `reference_vikunja_recurrence_model.md`). A weekly Wed-only habit gets 1 scheduled day per week; a daily habit gets 7. The percentage is computed against the actual scheduled cadence, NEVER against the calendar 7-day window. | Pending |
| FR-005 | Helper computes the prior-week baseline by running the same query against the prior 7-day window. Returns a non-zero baseline when the operator actually completed habits in the prior period. The uniform-zero pattern observed in the 2026-06-08 message is a regression class to test against explicitly. | Pending |
| FR-006 | Non-habit tasks (any task in project 13 with `repeat_after == 0`, OR tasks outside project 13) NEVER appear in the helper output. The "Upload cardiac lab history" class of one-off task is filtered out at the helper layer, not in the agent's render step. | Pending |
| FR-007 | `scripts/habits/query_active_habits_v2.py` (morning check-in query) is migrated to use the shared `vikunja_client`. Pre/post regression run against the existing test fixtures returns identical task lists. Existing tests pass without modification beyond the import line. | Pending |
| FR-008 | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` gains an output-discipline section mirroring capture's Hard Rules (capture lines ~33–84). The three Hard Rules forbid: (a) preamble before the identity line in any user-facing message; (b) between-tool-calls narration; (c) any text before `Sent by felix-admin-habits:<model>` in cron-fired announce messages. | Pending |
| FR-009 | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` documents the weekly-report procedure: invoke the helper, parse JSON, render to a WhatsApp turn-summary with deterministic format (identity header, one row per habit, percentages, overall footer). The pre-existing "weekly reports out of scope" statement is removed or revised to reflect the new in-scope reality. | Pending |
| FR-010 | `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` and `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` are audited for the same output-discipline gap. If a sibling agent emits user-facing WhatsApp without the Hard Rules in place, the rules are added in this mission. If a sibling does not emit user-facing WhatsApp, an explicit comment to that effect is added to its standing orders. | Pending |
| FR-011 | Test coverage for the new client: ≥90% line and ≥85% branch on `scripts/common/vikunja_client.py`. Test coverage for the new weekly helper: ≥90% line and ≥85% branch on `scripts/habits/query_active_habits_weekly.py`. Both verified via `pytest --cov-branch --cov-fail-under=90`. | Pending |
| FR-012 | The new test surfaces include explicit regression tests for: (a) cardiac-task-class non-habit filtering, (b) recurring-on-weekday percentage math (Wed-only habit returns 100% when completed on the one Wed), (c) prior-week baseline returns non-zero against historical fixture data, (d) Vikunja-unreachable produces typed exception, (e) base-URL trailing-slash normalization, (f) redaction-safe error messages. | Pending |
| FR-013 | Every classification decision and downstream action in the new helper logs via the existing `log_action.py` observability stream. New action types added: `weekly_report_generated`, `weekly_report_failed`. The agent's render step logs `weekly_report_sent` after the turn-summary is composed. | Pending |
| FR-014 | The weekly cron's invocation pattern is verified at plan phase via `openclaw cron list --json` on office2. AGENTS.md's documented procedure matches the cron's actual trigger. The pre-existing "out of scope" / cron-firing contradiction is resolved by either updating AGENTS.md (this mission's approach) or, if plan phase finds the cron itself is misconfigured, by amending it. | Pending |

## Non-Functional Requirements

| ID | Description | Measurable threshold | Status |
|---|---|---|---|
| NFR-001 | Weekly helper execution latency. | ≤5 seconds at the 95th percentile under normal Vikunja load on office2. | Pending |
| NFR-002 | No silent drops in the weekly report path. | 100% of weekly cron ticks either produce a complete report OR surface a `weekly_report_failed` action log AND a `Weekly report unavailable: <reason>` WhatsApp message. Zero ticks produce a hallucinated report. | Pending |
| NFR-003 | Audit trail completeness. | 100% of weekly cron ticks produce a structured log_action entry. Existing morning-check-in log behavior preserved. | Pending |
| NFR-004 | Idempotency. | Running the helper twice with the same `--window` argument and the same Vikunja state produces byte-identical JSON output. | Pending |
| NFR-005 | Client + helper test coverage. | ≥90% line, ≥85% branch on `scripts/common/vikunja_client.py` AND `scripts/habits/query_active_habits_weekly.py` per FR-011. | Pending |
| NFR-006 | Migration zero-regression. | All pre-existing `tests/habits/` tests continue to pass after the `query_active_habits_v2.py` migration. No new flakes. | Pending |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Standard library only for the new client and helper (no `requests`, no third-party HTTP libs). Existing project pattern; matches the validate_calendar_event helper from mission #558. | Pending |
| C-002 | Reuse existing `log_action.py` observability stream. New action types extend the existing allowlist; no parallel telemetry mechanism. | Pending |
| C-003 | Reuse existing `scripts/common/vikunja_config.py::get_vikunja_base_url()` for base URL resolution. Do not introduce a parallel URL helper. | Pending |
| C-004 | Reuse existing project 13 + daily-habit filter discipline from `query_active_habits_v2.py` (per #556's `363685ea`). The weekly helper extends this filter to include recurring-on-weekday habits per their Vikunja `repeat_after` + `repeat_mode` + `due_date`. | Pending |
| C-005 | The absolute privacy rule applies: no read, write, reference, or log of `~/second-brain/notes/04-Growth/_private/` content. Out-of-scope by mission boundary anyway, but stated for completeness. | Pending |
| C-006 | Change scope is Tier 3 (Logic / Workflow): client module, helper script, agent prompt edits, tests, architecture JSON updates. No host configuration, network, credential, port, or sudo-protected resource is modified. | Pending |
| C-007 | This mission introduces no new external services. The shared Vikunja client is new infrastructure code consuming existing Vikunja service + existing credential. | Pending |
| C-008 | The "two existing migrations" criterion from #542's original acceptance is intentionally relaxed to one migration in this mission per the umbrella plan in #562's comment. The second migration (escalation or enrichment) becomes a deliberate follow-up issue, NOT in this slice. | Pending |

## Success Criteria

- **SC-001 — Weekly report contains only habits**: in the 14 days following deployment, every weekly cron tick produces a report whose rows are all habits (project 13 with `repeat_after > 0`). No one-off tasks (the cardiac-class) appear.
- **SC-002 — Weekly report percentages match Vikunja data**: spot-check at least one cron tick by comparing the agent's reported percentage for one habit against Vikunja's actual check-in data for that habit over the same 7-day window. Match exactly.
- **SC-003 — Prior-week baseline reflects reality**: the same spot-check confirms the `(was X%)` annotation is the helper's actual prior-week query result, not a uniform 0%.
- **SC-004 — Weekly report identity-line discipline**: in the 14 days following deployment, every weekly-cron WhatsApp message begins literally with `Sent by felix-admin-habits:<model>`. No preamble.
- **SC-005 — Sibling agents audited**: at deployment time, `scripts/openclaw/agents/felix-admin-{escalation,tasker}/AGENTS.md` have been audited; rules added if missing OR explicit no-WhatsApp annotation present.
- **SC-006 — Client used by migrated v2 helper**: `scripts/habits/query_active_habits_v2.py` imports from `scripts.common.vikunja_client` and the morning-check-in cron's output remains identical to pre-migration.
- **SC-007 — Failure surfaces as failure, not hallucination**: if Vikunja is unreachable during a weekly cron tick (verifiable by deliberately blocking the office2 → vikunja path for a single tick), the WhatsApp message body says `Weekly report unavailable: <reason>` and a `weekly_report_failed` action is logged. No hallucinated data.

## Key Entities

- **VikunjaClient**: new class (or module-level functions) in `scripts/common/vikunja_client.py`. Stateless per-instance configuration (base URL, token, timeout). Methods: `get(path, **kwargs)`, `post(path, json=, **kwargs)`, `put`, `delete`. Returns parsed JSON or raises a typed exception.
- **VikunjaHttpError, VikunjaAuthError, VikunjaNotFoundError, VikunjaBadRequestError, VikunjaServerError, VikunjaTimeoutError**: exception hierarchy. All inherit from `VikunjaError` (base). All carry the request path; default-redacted bodies; opt-in verbose mode.
- **WeeklyHabitReport (JSON shape from the new helper)**: structured payload the agent consumes. Shape: `{"window_start_iso": ..., "window_end_iso": ..., "prior_window_start_iso": ..., "prior_window_end_iso": ..., "habits": [{"habit_id": int, "title": str, "scheduled_days_current": int, "completed_days_current": int, "percent_current": float, "scheduled_days_prior": int, "completed_days_prior": int, "percent_prior": float}], "overall_percent_current": float, "overall_percent_prior": float}`. Helper computes everything; agent only renders.
- **HabitClassification (existing, extended)**: the daily-habit-or-recurring-habit filter logic in `query_active_habits_v2.py`. Extended to include weekly-cadence recurring habits and exclude `repeat_after == 0` non-habits. Same predicate used by both v2 (morning) and weekly helpers.
- **Output discipline Hard Rules (text block)**: the three rules mirrored from capture's AGENTS.md. Inserted into felix-admin-habits' AGENTS.md (FR-008) and into siblings' AGENTS.md as the audit FR-010 requires. Plan phase decides whether the rules live as a duplicated text block per file or as a single shared file referenced from each AGENTS.md.
- **log_action event types (existing, extended)**: new entries `weekly_report_generated`, `weekly_report_failed`, `weekly_report_sent`. Extends the existing capture-and-habits allowlist.

## Assumptions

- Vikunja's `repeat_after` (in seconds) + `repeat_mode` enum encodes habit recurrence correctly per memory `reference_vikunja_recurrence_model.md`. Plan phase confirms by inspecting Kent's actual habit tasks via the existing morning-check-in query.
- Vikunja's check-in records for completed habits are queryable per day across a 14-day window (prior + current). Plan phase confirms via direct API probe.
- The weekly cron's actual cadence is verifiable via `openclaw cron list --json`. Plan phase verifies + documents.
- felix-admin-habits' agent runs on sonnet (per the 2026-06-08 message header `Sent by felix-admin-habits:sonnet`). Plan phase confirms; prompt-budget guidance assumes sonnet's window.
- The audit of felix-admin-escalation and felix-admin-tasker reveals one of two outcomes per agent: (a) the agent doesn't emit user-facing WhatsApp (annotation suffices), or (b) the agent does and lacks Hard Rules (add them). No third "rules exist but are different" case is anticipated; plan phase verifies.
- "WP04 T015" cited in the leaked monologue is either confabulation or refers to an unrelated prior mission. Plan phase resolves; if real, the prior context informs current design.

## Documentation Synchronization Requirement

Per DIR-005 and the kg-automation change-control protocol, this mission's merge MUST include synchronized updates to the following docs in the same PR (deferring to follow-on issues is an anti-pattern per memory `feedback_migration_no_vestiges.md`):

- `docs/design/architecture/data/service-inventory.json` — felix-admin-habits capability summary (revised: weekly-report capability now backed by deterministic helper, replacing LLM improvisation). felix-admin-escalation and felix-admin-tasker capability summaries updated to note output-discipline rules in place (if applicable per the audit). New entry or sub-note for the shared `vikunja_client` infrastructure.
- `docs/design/architecture/data/data-flows.json` — new flow: `weekly cron → felix-admin-habits → query_active_habits_weekly.py → vikunja_client → Vikunja API → WhatsApp turn-summary`. Sibling to the existing morning-check-in flow.
- `docs/design/architecture/data-flows.md` — narrative description of the new weekly-habit-report flow.
- `docs/design/architecture/data/signal-to-doc-map.json` — verify `change_class: service-modified` and `change_class: data-flow-added-or-modified` `doc_targets` arrays cover the docs touched.
- `tests/common/` (or wherever the existing client-style tests live) — unit tests for the new `vikunja_client.py`.
- `tests/habits/` — unit tests for the new weekly helper; regression-augmented for the migrated v2.

## Out of Scope

- Second existing helper migration to the shared client (e.g., `scripts/escalation/` or `scripts/enrichment/`). Documented as a deliberate follow-up issue per #562's umbrella comment; honors the gap-fill answer of "one migration only" at specify time.
- Voice / UX changes to the weekly report beyond fixing the data quality. The ASCII bar chart format from the existing 2026-06-08 message is acceptable; this mission preserves it.
- New habit-tracking features (streaks, missed-day detection, milestone alerts). Future work.
- Changes to Vikunja itself, habit data model, or the morning check-in's behavior (the morning path already works post-#556).
- Changes to the cron infrastructure beyond verifying the existing weekly cron's configuration. If the cron itself is misconfigured (e.g., wrong cadence), plan phase decides whether to amend in this mission or file follow-up.
- The inbox-cleanup bug filed at #563. Separate surface (prescan archiver), separate mission.

## Cross-references

- **kentonium3/kg-automation#562** — source umbrella issue (spec-ready). This mission addresses #562 in full.
- **kentonium3/kg-automation#542** — foundation issue (shared Vikunja client). This mission ships the foundation with one migration; second migration deliberately deferred.
- **kentonium3/kg-automation#561** — co-shipped output-discipline issue. This mission addresses #561 in full including the sibling-agent audit.
- **kentonium3/kg-automation#556** — precedent: morning-check-in fix via `363685ea` (sync pagination + project 13 scope). The weekly helper mirrors that fix's discipline.
- **Felix Constitution** — `docs/constitution/FELIX-CONSTITUTION.md` (Directive 6 scripts-vs-LLM split; Directive 5 documentation standards; Directive 8 operational symptom required for bugs).
- **Memory notes**: `reference_vikunja_recurrence_model.md` (recurrence model), `reference_vikunja_filter_gotchas.md` (server-side filter rejection class), `reference_vikunja_post_partial_replace.md` (POST partial-replace zeros fields), `feedback_scripts_vs_llm.md` (Directive 6 split), `feedback_audit_judgment_scripts_for_bug_class.md` (audit-as-acceptance discipline), `feedback_architecture_docs_first.md` (consult arch JSONs before SSH probing).

## Spec-ready criteria

- [x] **Executive Summary** states what the feature delivers in 2-3 sentences
- [x] **Problem Statement** captures current vs target state concretely
- [x] **Study These Files First** lists internal pointers (via the source-issue spec-ready bodies and the Cross-references section)
- [x] **Functional Requirements** has at least one FR with success criteria
- [x] **Out of Scope** lists explicit exclusions
- [x] **Architecture Impact** identifies affected JSON files
- [x] **Constitutional Compliance** addressed throughout the FRs + Constraints
- [x] **Design-time discipline** — deterministic-vs-stochastic split called out explicitly in FRs (FR-001/003/004/006/007 are deterministic; the agent's rendering of the helper output is the stochastic surface; the LLM never computes data)

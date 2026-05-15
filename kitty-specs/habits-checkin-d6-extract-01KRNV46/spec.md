# Mission Spec: Habits morning check-in — extract Steps 1-4 to helper scripts (D6)

**Mission**: `habits-checkin-d6-extract-01KRNV46`
**Type**: software-dev
**Target branch**: main → main (merge target)
**Tracks**: [#282](https://github.com/kentonium3/kg-automation/issues/282) (spec-ready feature issue)
**Parent epic**: [#281](https://github.com/kentonium3/kg-automation/issues/281) (Felix-wide Directive 6 audit)
**Constitution**: applies [Directive 6](../../docs/constitution/FELIX-CONSTITUTION.md) per [helper-script-conventions](../../docs/design/helper-script-conventions.md)

---

## Intent Summary

Refactor the `felix-admin-habits` agent's daily morning check-in path so that Steps 1-4 (deterministic operations — TZ-aware date, Vikunja query + filter, due_date setting, completion exclusion) are executed by helper scripts rather than the agent's prompt. Steps 5-6 (Format check-in, Output discipline — genuine LLM judgment) remain in-prompt. The mission is **behavior-preserving** end-to-end — Kent's WhatsApp check-in at 7:05 AM ET should be indistinguishable pre- and post-refactor on a representative day.

The mission is the first concrete application of Constitution Directive 6 and exercises the helper-script conventions (Phase 3 draft) as the authoritative implementation guidance.

---

## User Scenarios & Testing

### Primary Scenario — Daily check-in (happy path)

- **Trigger**: OpenClaw cron `habits-morning-checkin` fires at 11:05 UTC (7:05 AM ET).
- **Agent flow**: `felix-admin-habits` runs Steps 1-6 of its standing orders.
- **Observable outcome**: Kent receives a WhatsApp message at ~7:05 AM ET with the identity header `Sent by felix-admin-habits:sonnet` followed by today's habit check-in list, numbered, with the reply-instruction tail.
- **Acceptance**: post-refactor message is line-by-line identical to a pre-refactor reference message captured on the same calendar day class.

### Edge Cases

| # | Scenario | Expected behavior |
|---|---|---|
| 1 | All habits already complete for today | Agent replies `All habits complete for today.` (10 lines or fewer). No regression on existing AGENTS.md Step 5 rule. |
| 2 | Some habits marked `(PAUSED)` | Paused habits are excluded by `query_active_habits.py`. Final message contains no paused habits. |
| 3 | DST transition day (March) | `compute_today.py` returns offset `-04:00` post-transition; `set_due_dates.py` writes `YYYY-MM-DDT23:59:59-04:00`. No off-by-one date errors (must not regress #112). |
| 4 | Standard time transition day (November) | `compute_today.py` returns offset `-05:00`; `set_due_dates.py` writes `YYYY-MM-DDT23:59:59-05:00`. |
| 5 | Vikunja API fails for one habit in Step 3 (set_due_date) | `set_due_dates.py` logs the failure to stderr, continues with remaining habits, exits 1 to signal partial failure. Agent surfaces partial-failure state in operational logs but still produces the check-in message for habits that succeeded. |
| 6 | Vikunja completely unreachable (Step 2 query fails) | `query_active_habits.py` exits 1 with a stderr message. Agent's failure-handling subsection logs the error and does NOT send a broken check-in to Kent's WhatsApp. (Convention § 6.) |
| 7 | Cron runs after 8 PM ET (UTC has rolled over) | `compute_today.py` correctly resolves to the calendar day's ET-local date, not UTC. (Issue #112 forcing function.) |
| 8 | Empty Habits project (no tasks at all) | `query_active_habits.py` returns empty list, exits 0. Agent message: `All habits complete for today.` |
| 9 | Habit with malformed frequency description | `query_active_habits.py` excludes habit with a warning to stderr. Does NOT halt the workflow. |

---

## Functional Requirements

| ID | Title | Status | Description |
|---|---|---|---|
| FR-001 | TZ-aware date / day helper | proposed | `scripts/habits/compute_today.py` returns today's day-of-week, date, ET offset, and end-of-day-ET ISO timestamp. Output is single-line JSON. |
| FR-002 | Active habit query + filter helper | proposed | `scripts/habits/query_active_habits.py` queries Vikunja Habits project, filters by frequency table (Daily, Daily (evening), Mon-Sat, Mon/Wed/Fri), excludes `(PAUSED)` and `done: true`, returns scheduled habits for the input day. JSON stdout. |
| FR-003 | Due-date setting helper | proposed | `scripts/habits/set_due_dates.py` sets `due_date` end-of-day-ET on a list of habit IDs. Continues on per-habit failure; aggregates results. JSON stdout. |
| FR-004 | Completion exclusion helper | proposed | `scripts/habits/exclude_completed.py` fetches comments for each habit ID, filters out any with today's completion state (`complete`/`rescheduled`/`will-not-do`). JSON stdout. |
| FR-005 | AGENTS.md refactor | proposed | Steps 1-4 of `felix-admin-habits/AGENTS.md` replaced with helper invocations + JSON parsing. Step 5 (Format) feeds on structured output from Step 4. Step 6 (Output discipline) unchanged. New "Failure handling" subsection per conventions § 6. |
| FR-006 | Service inventory update | proposed | `docs/design/architecture/data/service-inventory.json` `habit-checkin` entry adds `config_files` references to the 4 helpers; `updated_by` references this mission. |
| FR-007 | End-to-end smoke test | proposed | Manual `openclaw cron run habits-morning-checkin` executes successfully on office2 post-deploy; WhatsApp message produced is line-by-line identical to a pre-refactor reference message captured on the same day class. |

---

## Non-Functional Requirements

| ID | Title | Status | Threshold |
|---|---|---|---|
| NFR-001 | Helper CLI contract | proposed | Each helper accepts argparse long-form flags; exits 0 on success, 1 on operational error, 2 on usage error; emits final stdout line `SUMMARY: key=value …`. (Per conventions § 2-3.) |
| NFR-002 | Behavior preservation | proposed | Post-refactor agent output on a representative calendar day is **line-by-line identical** to a pre-refactor reference message. Diff is empty. |
| NFR-003 | AGENTS.md size reduction | proposed | Post-refactor `AGENTS.md` line count is **≤ 300** (target 200). Pre-refactor: 478. |
| NFR-004 | TZ correctness | proposed | `set_due_dates.py` writes ISO timestamps with explicit ET offset (`-04:00` EDT or `-05:00` EST). **Never** emits a `Z` (UTC) suffix. Verified by unit test covering DST/EST transition dates. |
| NFR-005 | Helper test coverage | proposed | Each of FR-001…FR-004 has pytest tests covering happy path, at least one edge case from the Edge Cases table above, and at least one failure mode. Test files at `tests/habits/test_<helper>.py`. |
| NFR-006 | Idempotency | proposed | Each helper, given identical input, produces identical output and identical observable side effects (Vikunja state unchanged on second invocation). Verified by unit test where applicable. |
| NFR-007 | Partial-failure resilience | proposed | `set_due_dates.py` and `exclude_completed.py` continue on per-habit failure, log to stderr, and signal partial state via exit code 1 with structured stdout listing succeeded/failed IDs. |
| NFR-008 | Deploy footprint | proposed | All 4 helpers deployed to `/home/claude/kg-automation/scripts/habits/` on office2; updated AGENTS.md deployed to `/data/services/openclaw/habits-agent/AGENTS.md`. Deploy script or documented manual scp sequence. |

---

## Constraints

| ID | Title | Description |
|---|---|---|
| C-001 | No model migration | Sonnet → Haiku model assignment change is **explicitly out of scope** for this mission. Deferred to a follow-up after ~5 days of stable runs validate behavior preservation. |
| C-002 | No action-logging restructure | Current action-logging boundary (agent invokes `log_action.py` directly) is preserved exactly. No helpers invoke `log_action.py`. Boundary decisions deferred per Discovery Q2. |
| C-003 | No library extraction | `scripts/lib/vikunja.py` is NOT created in this mission. Per helper-script-conventions § 9 "don't pre-extract" guardrail — Vikunja CRUD primitives stay inline in each helper until a second mission needs the same primitives. |
| C-004 | Behavior-preserving refactor | The mission must not change the WhatsApp output Kent sees, the Vikunja state mutations performed, or the action-log entries written. Only the locus of execution changes (prompt → script). |
| C-005 | Regular change mode | This is NOT a bulk edit (no rename-X-to-Y pattern). `change_mode: "regular"` in meta.json. Confirmed during Discovery's Bulk-Edit Detection. |
| C-006 | No Vikunja schema changes | The Habits project structure, task frequency convention (description-field parsing), and comment format are unchanged. Helpers consume the existing schema; do not modify it. |
| C-007 | Reference helpers as implementation model | New helpers follow the patterns established by `handle_drift_events.py` (argparse + SUMMARY: line), `prescan.py` (JSON-stdout-for-agent-consumption), and `inject_parse_error_marker.py` (atomic write + mode preservation). |

---

## Success Criteria

Measurable, technology-agnostic outcomes that validate mission completion:

1. **No regression on Kent's WhatsApp experience** — daily 7:05 AM ET check-in continues at the same time, in the same format, with the same content, post-deploy.
2. **Operational complexity reduced** — `AGENTS.md` is at least 35% smaller (478L → ≤310L; target 200L).
3. **Hallucination paths eliminated for Steps 1-4** — TZ-offset rules, frequency-table parsing, comment-format writing, and completion-state filtering no longer rely on LLM reasoning. Each is now a script with verifiable input/output.
4. **All helpers pass their automated test suites** — every helper has tests covering at minimum happy path, one edge case, and one failure mode; all suites pass.
5. **Smoke test confirms parity** — manual cron run on office2 produces a WhatsApp message that matches a pre-refactor reference message line-by-line on a representative day class.
6. **#112 regression check** — no off-by-one date errors observable in Vikunja's Today filter after a daily run. Habits appear with the correct end-of-day-ET due_date.
7. **First scheduled production run succeeds** — the daily cron at the next 7:05 AM ET after deploy completes without alert, log error, or operational regression.

---

## Key Entities

| Entity | Definition |
|---|---|
| **Habit** | A Vikunja task in the "Habits" project. Carries a frequency descriptor in its `description` field (e.g., "Daily", "Mon-Sat"). May be marked `(PAUSED)` to opt-out temporarily. |
| **Check-in message** | A WhatsApp text delivered to Kent at 7:05 AM ET listing today's scheduled habits, one per line, numbered, with a tail reply-instruction. |
| **Completion comment** | A Vikunja comment in the form `[Felix] YYYY-MM-DD \| {complete\|rescheduled\|will-not-do} \| optional note`. Authoritative record of daily completion state. |
| **Helper invocation** | A `python3 scripts/habits/<helper>.py <args>` shell call from the agent's AGENTS.md. Returns JSON on stdout and a final `SUMMARY:` line; exits with a documented code. |
| **ET offset** | The current Eastern Time UTC offset: `-04:00` during EDT (March–November) or `-05:00` during EST (November–March). Computed by `compute_today.py`. |
| **End-of-day-ET ISO timestamp** | `YYYY-MM-DDT23:59:59<ET_OFFSET>`. Used as `due_date` value to make habits visible in Vikunja's Today filter without prematurely marking them overdue (the #112 fix). |

---

## Assumptions

These are taken for granted; the plan phase should validate the load-bearing ones before implementation begins:

1. **Vikunja API surface is stable.** The endpoints the helpers call (`GET /projects`, `GET /tasks/all`, `PUT /api/v1/tasks/{id}`, `GET /tasks/{id}/comments`) match what the agent currently uses. No API version migration is in flight.
2. **Vikunja auth credentials are accessible to office2-side scripts.** Currently used by the agent's API calls; helpers consume the same credential surface. (Plan phase should confirm the exact mechanism — env var, config file, or skill-document parse — and document it in the plan.)
3. **office2 has Python 3 with `requests` (or equivalent) available.** Already validated by other Python helpers running on office2.
4. **`TZ=America/New_York` data is present on office2.** Required by `compute_today.py`. Standard Linux distribution; not expected to be a gap.
5. **The cron mechanism for `habits-morning-checkin` is unchanged.** OpenClaw cron continues to invoke the agent at 11:05 UTC; no changes to scheduling.
6. **Pre-refactor reference output can be captured.** A representative check-in message from the current Sonnet-driven path is available for line-by-line diff comparison post-refactor. (Plan phase: identify capture procedure — e.g., screenshot of WhatsApp message + transcript from agent session log.)
7. **Behavior preservation is validated empirically, not formally.** A single successful smoke run + a single successful production run is sufficient evidence. We do NOT need to mathematically prove output equivalence; we rely on observed parity.
8. **No upstream OpenClaw changes during the mission window.** OpenClaw cron behavior, agent invocation contract, and tool registry are stable for the duration.

---

## Dependencies

- **Constitution Directive 6** ([`docs/constitution/FELIX-CONSTITUTION.md`](../../docs/constitution/FELIX-CONSTITUTION.md)) — the principle being applied
- **Helper-script-conventions (status: draft)** ([`docs/design/helper-script-conventions.md`](../../docs/design/helper-script-conventions.md)) — the operational rules implementation must follow
- **Reference helpers**:
  - [`scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py`](../../scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py)
  - [`scripts/inbox/prescan.py`](../../scripts/inbox/prescan.py)
  - [`scripts/inbox/inject_parse_error_marker.py`](../../scripts/inbox/inject_parse_error_marker.py)
- **Existing agent context**:
  - [`scripts/openclaw/agents/felix-admin-habits/AGENTS.md`](../../scripts/openclaw/agents/felix-admin-habits/AGENTS.md) — the prompt being refactored
  - [`docs/design/architecture/felix-d6-survey.md`](../../docs/design/architecture/felix-d6-survey.md) — Phase 1 survey justifying this mission's priority

---

## Notes for Plan Phase

- The `target_branch` and `merge_target_branch` are both `main`. No branch divergence expected.
- The agent runs on office2 (Sonnet 4.6). Deploy targets two paths: `/home/claude/kg-automation/scripts/habits/` (source-of-truth) and `/data/services/openclaw/habits-agent/AGENTS.md` (deployed prompt).
- The smoke test must run on office2 (where the agent actually runs). Local Python tests on the Mac validate logic; only the office2 run validates the integration.
- Codex (per Kent's directive) will perform code review during `/spec-kitty.review`. Implementation by Claude.
- Mission uses the implement-review path (skill: `spec-kitty-implement-review`).

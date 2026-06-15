# Implementation Plan: Trustworthy weekly habit report

**Branch**: `kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7` (coord) → `main` (target)
**Date**: 2026-06-15
**Spec**: [`spec.md`](spec.md)
**Source issue**: [#605](https://github.com/kentonium3/kg-automation/issues/605)
**Related epic**: [#281](https://github.com/kentonium3/kg-automation/issues/281) (Felix-wide Directive 6 audit)

## Summary

Two failure modes in the weekly habit accountability report converge on one mission: (a) the helper reads Vikunja's volatile `done_at` field — a single timestamp per task, reset on each daily-recurrence cycle — instead of the canonical append-only `habits-history.jsonl`, so daily habits report 0% completion even when Kent completed them multiple times; and (b) the cron fires Sunday 22:00 ET, three hours before the reporting window closes. The fix routes the weekly query through the canonical store via a new habits-domain wrapper, moves WhatsApp message rendering into the helper, adds an architectural test that ratchets the canonical-read rule, reschedules the cron to Monday 06:00 ET, and refreshes the architecture documentation.

## Technical Context

**Language/Version**: Python 3.13 (existing kg-automation toolchain)
**Primary Dependencies**: `scripts/common/state_log.py` (existing; provides domain-scoped JSONL `read`/`append`/`validate_record`), `scripts/common/vikunja_client.py` (existing; retained for current-state queries only post-fix), pytest 7+, `datetime` + `zoneinfo` (stdlib)
**Storage**: `/data/services/openclaw/state/habits-history.jsonl` on office2 (read-only consumer; canonical primary written by `record_completion.py` / `sweeper.py` / `backfill_jsonl_from_comments.py`)
**Testing**: pytest with a golden-week fixture covering daily / day-specific / week-bounded habit patterns; AST-based architectural test scanning `scripts/habits/*.py` imports against a file-level allowlist
**Target Platform**: office2 (Ubuntu 24.04 LTS) for runtime; macOS 13+ / Python 3.13 for local CI parity
**Project Type**: single — kg-automation's existing `scripts/<domain>/` + `tests/<domain>/` + `tests/architectural/` layout
**Performance Goals**: Weekly helper completes ≤5s on office2 (NFR-001 byte-stability); architectural test completes ≤5s standalone (NFR-002)
**Constraints**: WeeklyHabitReport JSON schema backward-compatible (NFR-005); helper output byte-stable for same JSONL state + same wall-clock window (NFR-001); rendered WhatsApp text byte-stable for same JSON input (NFR-004); openclaw cron change deploys via `deploys/queued/<name>.yaml` manifest discipline (C-006)
**Scale/Scope**: ~10 active habits × 365 days/year ≈ 3,650 completion events/year in `habits-history.jsonl`; one weekly cron tick

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Felix Constitution + Engineering Principles governance applies; spec-kitty charter is loaded but does not introduce additional mission-blocking gates here. Key alignment:

| Directive | Compliance |
| --- | --- |
| **D5 (machine-readable docs are authoritative)** | IC-06 updates `docs/design/architecture/data/service-inventory.json`, `data-flows.json`, and `signal-to-doc-map.json` to reflect the canonical-read path. Narrative counterparts updated in the same change. |
| **D6 (deterministic vs LLM split)** | This mission is the canonical D6 application: all percentage math, window math, classification, and WhatsApp rendering move into helpers; the agent prompt only sequences and surfaces errors. Mirrors the pattern from #253 / #259 / #277. |
| **D8 (operational symptom required for bug issues)** | #605 names symptom (0% for completed habits + cron fires early), observer (Kent), cost-of-doing-nothing (accountability loop collapses; primitive for analysis epic is unusable). |
| **Helper conventions (`docs/design/helper-script-conventions.md`)** | New wrapper follows the helper-tier convention: pure Python module, CLI invocation contract not required for IC-01 (library), but IC-02 (the rewritten `query_active_habits_weekly.py`) retains its existing argparse CLI contract per prior mission. Tests live in `tests/habits/`. |
| **Rebaseline obligation (#557)** | Audited surfaces touched: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (openclaw agent prompt) and `deploys/queued/<name>.yaml` (deploy script). Merge commit MUST record `Rebaseline: completed at <ts>` after operator runs the canonical reset. |

**Gate verdict**: PASS. No charter violations. No `[NEEDS CLARIFICATION]` markers required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/
├── spec.md              # /spec-kitty.specify output (committed)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output
    ├── habits_history_wrapper.md
    ├── weekly_helper_cli.md
    └── architectural_test.md
```

### Source Code (repository root)

```
scripts/
├── common/
│   ├── state_log.py             # EXISTING — used by IC-01
│   └── vikunja_client.py        # EXISTING — current-state queries only post-fix
└── habits/
    ├── history.py               # NEW — IC-01 habits-domain wrapper
    ├── query_active_habits_weekly.py   # REWRITE — IC-02 canonical-read + rendering
    └── (other existing habits helpers untouched in this mission)

tests/
├── architectural/
│   └── test_habits_history_canonical_read.py   # NEW — IC-03 ratchet
└── habits/
    ├── test_history.py          # NEW — IC-01 unit tests
    ├── test_query_active_habits_weekly.py  # UPDATED — IC-02 golden-week fixture
    └── fixtures/
        └── golden_week_jsonl.py # NEW — golden-week fixture per FR-008

deploys/
└── queued/
    └── reschedule-felix-admin-habits-weekly-cron.yaml   # NEW — IC-05

scripts/openclaw/agents/felix-admin-habits/
└── AGENTS.md                    # UPDATED — IC-04 strip in-prompt rendering, update cron time

docs/design/architecture/
├── data/
│   ├── service-inventory.json   # UPDATED — IC-06 canonical-read description
│   ├── data-flows.json          # UPDATED — IC-06 corrected weekly-tick flow
│   └── signal-to-doc-map.json   # UPDATED — IC-06 entry refreshed
└── services.md                  # UPDATED — IC-06 narrative counterpart if it covers this surface
```

**Structure Decision**: Single project. Aligns with kg-automation's existing helper / test / deploys / docs layout. No new top-level directories.

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into executable WPs.

### IC-01 — Habits-domain query wrapper

- **Purpose**: Expose habit-shaped read operations (window-bounded completion events, per-habit completion rate, scheduled-vs-completed counts) on top of generic `state_log`. The wrapper is the single read API for any caller — current weekly helper, future trend-analysis helper, ad-hoc analysis — so nobody re-derives JSONL semantics.
- **Relevant requirements**: FR-002, FR-003, FR-007, NFR-001, NFR-005, SC-005
- **Affected surfaces**: `scripts/habits/history.py` (NEW), `tests/habits/test_history.py` (NEW)
- **Sequencing/depends-on**: none
- **Risks**: API design must accommodate both window-bounded (weekly) and per-habit (trend) use cases without bloating. Decision (per research.md): start with three operations (`completion_events_in_window`, `completion_rate_for_habit`, `scheduled_vs_completed_for_habit`). Additions later if trend-analysis needs more.

### IC-02 — Weekly helper rewrite (canonical-read + rendering)

- **Purpose**: Switch `scripts/habits/query_active_habits_weekly.py` to read from `habits-history.jsonl` via the IC-01 wrapper (not Vikunja `done_at`), and move WhatsApp message rendering into the helper so the LLM is not in the data path.
- **Relevant requirements**: FR-002, FR-005, FR-006, FR-007, FR-009, FR-010, NFR-001, NFR-004, NFR-005, SC-001, SC-002, SC-004
- **Affected surfaces**: `scripts/habits/query_active_habits_weekly.py` (REWRITE), `tests/habits/test_query_active_habits_weekly.py` (UPDATE), `tests/habits/fixtures/golden_week_jsonl.py` (NEW)
- **Sequencing/depends-on**: IC-01 (uses wrapper)
- **Risks**: WeeklyHabitReport JSON schema MUST remain backward-compatible. The new `rendered_text` field is additive and explicitly declared optional in the existing payload contract. Date-range label fix (FR-006) is a 7-day inclusive window string ("Mon Jun 8 – Sun Jun 14"), not a calendar span that double-counts the boundary day. Vikunja project 13 list-fetch for habit titles + classification remains via `VikunjaClient.get_tasks(...)` (current-state, not completion-history — explicitly allowlisted for IC-03).

### IC-03 — Architectural test ratchet

- **Purpose**: Fail the build if any script under `scripts/habits/*.py` imports `VikunjaClient` for completion-history queries. Current-state queries remain permitted via a file-level allowlist with explicit reason markers.
- **Relevant requirements**: FR-004, NFR-002, NFR-003, SC-003
- **Affected surfaces**: `tests/architectural/test_habits_history_canonical_read.py` (NEW)
- **Sequencing/depends-on**: IC-02 (test goes RED until IC-02 lands; then GREEN)
- **Design**: AST-based scan of `scripts/habits/*.py`. Files that import `VikunjaClient` must be in an explicit allowlist in the test file with a one-line reason. After IC-02 lands, `query_active_habits_weekly.py` is REMOVED from the allowlist (it no longer imports VikunjaClient). A negative-control test deliberately adds VikunjaClient to a fixture file and verifies the test fails with file+line diagnostics.
- **Risks**: The allowlist must be specific enough that adding a new current-state helper doesn't accidentally trip the rule — but loose enough that future maintainers don't bypass without thinking. Decision: allowlist by exact filename; reviewers see allowlist diffs in PR.

### IC-04 — Agent prompt simplification

- **Purpose**: Strip the in-prompt rendering logic from `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`. The agent's weekly role collapses to: invoke helper, post helper-rendered text verbatim to WhatsApp, preserve `Sent by felix-admin-habits:<model>` identity line.
- **Relevant requirements**: FR-005, FR-010, C-005
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
- **Sequencing/depends-on**: IC-02 (helper must emit `rendered_text` before agent prompt can rely on it)
- **Risks**: AGENTS.md effective size budget is ~14-15K source chars per memory `reference_openclaw_gotchas.md`. Current file is 282 lines / well under budget. Weekly section shrinks; budget stays well clear.

### IC-05 — Cron reschedule via deploy manifest

- **Purpose**: Move openclaw cron from `0 22 * * 0` (Sunday 22:00 ET) to `0 6 * * 1` (Monday 06:00 ET) via `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml`. Update AGENTS.md cron reference text in the same change.
- **Relevant requirements**: FR-001, C-006
- **Affected surfaces**: `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` (NEW), `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` cron reference paragraph
- **Sequencing/depends-on**: IC-04 (agent prompt may also reference the new cron time, so coordinate the AGENTS.md edits)
- **Risks**: Operator must apply the deploy manifest (via felix-deployer) post-merge. Verify openclaw cron primitive (in `scripts/deploy/lib/`) supports the desired cron expression and TZ. Confirm TZ handling — openclaw runs in `America/New_York`? Or UTC and the cron is `0 10 * * 1`? Research item.

### IC-06 — Architecture documentation update

- **Purpose**: Update `docs/design/architecture/data/service-inventory.json` (felix-admin-habits weekly tick description), `data-flows.json` (weekly-tick flow), and `signal-to-doc-map.json` to reflect the canonical-read path. Update any narrative counterparts.
- **Relevant requirements**: FR-011, SC-006
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/data/data-flows.json`, `docs/design/architecture/data/signal-to-doc-map.json`, `docs/design/architecture/services.md` if it carries the same description
- **Sequencing/depends-on**: IC-02 (description must be true after IC-02; updating ahead of code lands lying docs)
- **Risks**: Per kg-automation CLAUDE.md "Standing requirement": these updates MUST land in the same merge as the implementation. Don't defer to a follow-on.

## Complexity Tracking

*No charter violations — section intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| _none_ | — | — |

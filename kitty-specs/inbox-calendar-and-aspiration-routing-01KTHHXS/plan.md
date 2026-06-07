# Implementation Plan: Inbox calendar and aspiration routing

**Branch**: `kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/spec.md`

## Summary

Capture agent gains explicit routing for three new block classes — calendar event, aspiration/musing, and Someday item — and tightens the existing "task or action item" rule. Calendar events with complete fields are delegated to Felix main via the openclaw agent channel; Felix main creates the event in Google Calendar via the existing `gog` skill. Incomplete calendar events surface a clarification prompt in the capture agent's WhatsApp turn-summary, with a pending-calendar-clarifications JSONL state file recording each open clarification so Kent's WhatsApp reply can resolve it. Aspirations route to dated journal entries; Someday-shaped items route to Vikunja project `Someday` (id 4) with no due date. A new deterministic helper (`scripts/calendar/validate_calendar_event.py`) handles completeness validation and natural-language → RRULE conversion per Felix Constitution Directive 6.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/inbox/` helpers; office2 Ubuntu 24.04 ships Python 3.12 as default).
**Primary Dependencies**: Standard library only for the helper script (`json`, `dataclasses`, `re`, `datetime`, optionally `dateutil` for RRULE expansion if needed beyond plain string assembly). Existing kg-automation surfaces consumed (not new dependencies): `scripts/common/vikunja_config.py` (Vikunja base-URL helper), `scripts/inbox/append_routing_entry.py` (routing-log dedup substrate), `scripts/openclaw/observation/log_action.py` (audit trail), `gog calendar create` v0.19.0 (Google Calendar write via Felix main), `openclaw agent --agent main` (capture → Felix main delegation channel).
**Storage**: New JSONL file at `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` (alongside existing `inbox-routing.jsonl`). Append-and-rewrite (read all, filter resolved, write back) on resolve/timeout. No DB.
**Testing**: pytest with branch coverage (`pytest --cov=scripts/calendar --cov-branch`) following the pattern in `tests/inbox/`. Unit tests for the validator; classifier regression set as a fixture file consumed by an end-to-end-style test that exercises the prompt against curated input blocks. Coverage threshold: ≥90% line, ≥85% branch on the new validator.
**Target Platform**: Ubuntu 24.04 LTS on office2 (production); macOS Darwin 25.5.0 for dev/test on Kent's Mac.
**Project Type**: single — additions to existing repo (`scripts/`, `tests/`, `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`).
**Performance Goals**: ≤30s per inbox file at 95th percentile per NFR-001 (matches existing capture cron tick budget).
**Constraints**: Tier 3 change (logic/workflow). No host config, network, credentials, ports, or sudo-protected resources modified. Privacy boundary at `~/second-brain/notes/04-Growth/_private/` is absolute. Idempotency required: re-processing the same inbox file 10 consecutive times produces exactly one calendar event / journal append / Someday task per original block.
**Scale/Scope**: ~5 inbox files/day typical, ~30/day high. New helper script ~200 lines + tests. Capture agent prompt grows by ~80 lines (new routing rows, completeness logic, clarification UX). Felix main standing orders gain ~40 lines for the reply handler. Architecture JSON updates touch ~3 files.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context loaded via `spec-kitty charter context --action plan --json` (compact mode, directives confirmed):

| Directive | Applies? | How this plan satisfies |
|---|---|---|
| DIRECTIVE_001 — Architectural Integrity | Yes | Helper script is independently testable; agent prompt changes are localized to two AGENTS.md files; no cross-component leakage. |
| DIRECTIVE_003 — Decision Documentation | Yes | This plan documents the calendar-mechanism decision (use existing gog skill via Felix main delegation) and the reply-routing decision (state file is always written; receiving agent is Felix main per `openclaw doctor` confirmation). |
| DIRECTIVE_010 — Specification Fidelity | Yes | Plan derives strictly from spec FRs/NFRs/Cs; no scope expansion. Out-of-scope items (calendar updates, attendee invites, conflict detection) explicitly carried from spec. |
| DIRECTIVE_024 — Locality of Change | Yes | Calendar logic localized to `scripts/calendar/`; classification updates localized to capture's `AGENTS.md`; reply handler localized to Felix main standing orders. No cross-cutting refactors. |
| DIRECTIVE_031 — Context-Aware Design | Yes | Domain language section in spec defines the bounded context (block / calendar event / aspiration / Someday / active task). Plan respects those boundaries. |
| DIRECTIVE_033 — Targeted Staging | Yes | Implementation will stage only the expected deliverables per WP. No blanket `git add .` in WP prompts. |
| DIRECTIVE_034 — Test-First Development | Yes | Validator unit tests authored before validator implementation. Classifier regression set authored before classifier prompt changes. |
| DIR-001 — c4-incremental-detail-modeling | Yes | This plan is Layer 2 (Plan) of the C4 progression. Layer 3 (research.md) and Layer 4 (data-model.md + contracts/ + quickstart.md) follow below. Layer 5 (tasks) is the next phase, not in scope here. |
| DIR-002 — Privacy/security boundaries | Yes | C-005 in spec affirms the `04-Growth/_private/` absolute rule. No new privacy surface. |
| DIR-003 — Docs synchronized with workflow changes | Yes | See Documentation Sync section in spec; this plan preserves that requirement. |
| DIR-004 — Documentation standards | Yes | Plan and spec follow YAML-frontmatter conventions where applicable; mission artifacts use spec-kitty's conventions. |
| DIR-005 — Mission must include doc-sync requirement | Yes | Spec's "Documentation Synchronization Requirement" section enumerates the JSON + Markdown files that must update in the merge PR. |
| DIR-006 — Probe real environment | Yes | Live probing of office2 done during this plan phase. Surfaced corrections to spec assumptions (gog binary location, vikunja_config helper path, Vikunja Someday project id). All documented in research.md. |

**Gate verdict**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```
kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/
├── plan.md              # This file
├── spec.md              # Feature spec (committed 8d1394c9)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── checklists/
    └── requirements.md  # Specify-phase checklist (committed 0483d2f6)
```

### Source code (repository root, kg-automation)

```
scripts/
├── calendar/                              # NEW
│   ├── __init__.py
│   └── validate_calendar_event.py         # Deterministic completeness + RRULE helper
├── common/
│   └── vikunja_config.py                  # EXISTING (consumed by new code)
├── inbox/
│   ├── append_routing_entry.py            # EXISTING (consumed)
│   ├── prescan.py                         # EXISTING (consumed)
│   └── ... (other existing helpers)       # EXISTING
└── openclaw/
    └── agents/
        └── felix-admin-capture/
            └── AGENTS.md                  # MODIFIED — new routing rows + logic

tests/
├── calendar/                              # NEW
│   ├── __init__.py
│   ├── test_validate_calendar_event.py    # Validator unit tests
│   └── fixtures/
│       ├── complete_oneoff.json
│       ├── complete_weekly.json
│       ├── complete_monthly_by_dayofmonth.json
│       ├── complete_byweekday_of_month.json
│       ├── incomplete_no_start.json
│       ├── incomplete_no_end.json
│       └── ambiguous_recurrence.json
└── inbox/
    └── test_classifier_regression.py      # NEW: classifier regression set

docs/
└── design/
    └── architecture/
        ├── data/
        │   ├── service-inventory.json    # MODIFIED — capture+main capability entries; gog used_by extended
        │   ├── data-flows.json           # MODIFIED — three new flows added
        │   └── signal-to-doc-map.json    # MODIFIED — extend doc_targets for service-modified + data-flow-added
        └── data-flows.md                 # MODIFIED — narrative for the new inbox classification flows

ON OFFICE2 (deployed via existing post-merge sync — not modified by this mission):
- Felix main workspace at /home/claude/.openclaw/workspace/AGENTS.md
  → adds Calendar Reply Handler section (delivered as a workspace AGENTS.md edit
    in the mission's same diff, committed alongside capture's AGENTS.md update)
```

**Structure Decision**: Single-project layout. The mission delivers (a) a new deterministic helper script + tests under `scripts/calendar/` and `tests/calendar/`, (b) two AGENTS.md prompt updates (capture + Felix main workspace), (c) one new classifier regression test under `tests/inbox/`, (d) three architecture JSON updates + one narrative MD update. Deploy to office2 is by existing post-merge sync (out-of-scope for this mission).

## Phase 0: Research

Live-probe research (per DIR-006) completed during this plan phase. Full findings recorded in [research.md](./research.md). Headlines:

- **gog calendar create works as needed**: binary at `/home/linuxbrew/.linuxbrew/bin/gog` v0.19.0, signature `gog calendar create <calendarId> --summary --from --to [--rrule] [--location] [--description] [--start-timezone] [--end-timezone] [--attendees] -j`. `--rrule` accepts RFC 5545 RRULE strings (e.g., `"RRULE:FREQ=WEEKLY;BYDAY=TU"`). OAuth wired via systemd `openclaw-gateway-env` EnvironmentFile + `GOG_KEYRING_PASSWORD` (architecture-managed; no new credential work).
- **Felix main routes WhatsApp inbound**: confirmed via `openclaw doctor`. Agent `main` is the receiving agent for inbound replies.
- **`openclaw doctor` warning about Felix main's `message` tool**: not a blocker for this mission's reply-resolve flow (Felix main reads the JSONL state file and shells out to `gog`; no `message` channel action needed for the reply path itself). Out-of-scope; tracked separately as needed.
- **Vikunja Someday project**: confirmed `id=4, title="Someday"`. Vikunja base URL `https://office2.tail0f5f56.ts.net/api/v1` (no trailing slash). Token at `/data/services/openclaw/secrets/vikunja-api`. Vikunja Habits project at `id=13` (per memory `reference_speckitty_issue_416` and habits-fix commit context).
- **Calendar accounts**: `kent@intentional.biz` (owner) and `kentgale@gmail.com` (writer/shared). Default for inbox-routed events: `--account kent@intentional.biz --calendar primary`. Plan-phase decision: no calendar-picker logic in this mission; everything routes to Kent's primary on `kent@intentional.biz`. Routing to the shared `kentgale@gmail.com` calendar is out of scope (follow-up).
- **Recurrence boundary — RRULE is for Google Calendar only, NOT Vikunja**: this mission uses RFC 5545 RRULE strings (`RRULE:FREQ=WEEKLY;BYDAY=TU` etc.) exclusively for `gog calendar create --rrule`, i.e., Google Calendar events. Vikunja today uses a different recurrence encoding (`repeat_after` in seconds + `repeat_mode`) and does NOT speak RRULE; native RRULE support is in flight upstream at [go-vikunja/vikunja#2032](https://github.com/go-vikunja/vikunja/pull/2032) but not shipped. Since this mission never writes recurrence to Vikunja (calendar events are NEVER Vikunja tasks per spec FR-001 / FR-005 always-true rule; Someday tasks are one-off per FR-009), the Vikunja recurrence shape is not used here. Any future mission that adds Vikunja recurrence must use `repeat_after`/`repeat_mode` until #2032 lands.
- **vikunja_config public API**: `get_vikunja_base_url()` is the public function in `scripts/common/vikunja_config.py`. There is no `get_token` helper in that module; the token is loaded directly from `/data/services/openclaw/secrets/vikunja-api`. The vikunja base URL helper has a trailing-slash quirk (canonical config has trailing slash but the API rejects it) — separate concern, not mission scope.
- **Architecture-docs-first lesson recorded**: memory `feedback_architecture_docs_first.md` saved this session. The architecture JSONs in `docs/design/architecture/data/` are the canonical reference; SSH probes are for filling gaps in the JSONs, not the primary source.

## Phase 1: Design & Contracts

Design artifacts:

- [data-model.md](./data-model.md) — entities (CalendarEventPayload, PendingClarificationRecord, JournalEntryBlock, SomedayTaskRequest) with field tables, validation rules, and lifecycle.
- [contracts/validate_calendar_event.md](./contracts/validate_calendar_event.md) — stdin/stdout JSON contract for the new helper script.
- [contracts/capture_to_main_calendar_payload.md](./contracts/capture_to_main_calendar_payload.md) — structured payload contract for the `openclaw agent --agent main` delegation call.
- [contracts/pending_clarification_record.md](./contracts/pending_clarification_record.md) — JSONL line schema for the state file.
- [quickstart.md](./quickstart.md) — operator-runnable smoke test: submit a test inbox note with a calendar event, observe end-to-end behavior on office2.

## Re-evaluation of Charter Check (post-Phase 1)

All gates remain PASS. No new violations surfaced during research or design.

## Work-package strategy (advisory for /spec-kitty.tasks)

This section is advisory only — actual WP decomposition happens at `/spec-kitty.tasks` time. Recorded here so the eventual decomposition has context.

Anticipated WPs (all land in one mission merge per memory `feedback_speckitty_split_code_and_deploy_missions`; no code-merge-between-WPs dependency):

- **WP01 — Helper + classifier fixtures**: new `scripts/calendar/validate_calendar_event.py`, unit test suite, classifier regression fixture (~25 cases including historical misroutes from #556 and the trivia-night example from #324). Owned files: `scripts/calendar/**`, `tests/calendar/**`, `tests/inbox/test_classifier_regression.py`, `tests/inbox/fixtures/classifier_regression.json`.
- **WP02 — Capture agent prompt + routing logic**: revise `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Step 3 table (calendar / aspiration / Someday rows), add calendar completeness branch (invokes WP01's helper), add aspiration-detection rules, add Someday-detection rules, tighten task-rule, add new `log_action` types to allowlist, add clarification-prompt formatting for WhatsApp turn-summary. Owned files: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`.
- **WP03 — Felix main calendar reply handler**: revise Felix main workspace `AGENTS.md` to add a Calendar Reply Handler section that, on WhatsApp inbound, reads `pending-calendar-clarifications.jsonl`, matches the reply to the most recent open entry, invokes `gog calendar create` with completed args, removes the resolved entry, and confirms via WhatsApp turn-summary. Owned files: Felix main `AGENTS.md` (path resolved on office2 — for the kg-automation diff, this is committed under the workspace path captured in the deployed structure).
- **WP04 — Architecture JSON + narrative doc-sync**: update `docs/design/architecture/data/service-inventory.json` (felix-admin-capture + main capability entries + gog `used_by`), `docs/design/architecture/data/data-flows.json` (three new flow entries), `docs/design/architecture/data-flows.md` (narrative for the new flows), and `docs/design/architecture/data/signal-to-doc-map.json` (extend doc_targets if needed). Owned files: those four. Correction note: spec/plan originally referenced `agent-inventory.json` and `architecture/agents.md`; those files do not exist in this repo — agents are catalogued IN `service-inventory.json` and the canonical narrative is `data-flows.md`. Caught by `finalize-tasks --validate-only` on 2026-06-07.

WP dependency graph: WP01 is independent. WP02 references WP01's helper path. WP03 is independent (reads a state-file shape defined in spec.md / data-model.md, no code dependency on WP01). WP04 is independent. All four are mergeable in one mission merge.

## Complexity Tracking

*Fill ONLY if Charter Check has violations that must be justified.*

No charter violations. Table omitted.

---

## Branch contract (final reaffirmation per runbook)

- **Current branch at plan finish**: `kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS` (per setup-plan JSON output)
- **Planning/base branch**: `kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS` (per setup-plan JSON output — note: setup-plan returns current-branch as target during transitional window; actual merge target is `main` per the mission's `meta.json`)
- **Final merge target**: `main` (per `meta.json` at mission create)
- **Branch matches expected target**: `true` per setup-plan; the actual merge into `main` happens at `spec-kitty merge` time, which sources merge target from `meta.json` rather than `setup-plan`'s `merge_target_branch` field.

The setup-plan JSON's `merge_target_branch` reporting the current branch (rather than `main`) appears to be a 3.2.0rc37 oddity — same class as kg-automation#559. Logged but not blocking for this plan phase.

## Next phase

After plan.md and Phase 1 artifacts commit, the user runs `/spec-kitty.tasks` to decompose into the work packages outlined above. This command **STOPS** here per the spec-kitty.plan runbook's mandatory stop point.

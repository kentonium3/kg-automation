# Implementation Plan: Deterministic escalation + weekly-report crons

**Branch**: `fix/deterministic-cron-hardening` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/deterministic-cron-hardening-01KXA4PX/spec.md`

## Summary

Remove LLM improvisation from two failing Felix crons. Escalation gains a
deterministic candidate-enumeration helper (`scripts/escalation/enumerate_candidates.py`)
that paginates Vikunja `/tasks/all` and filters client-side per the escalation
§1 criteria; the `felix-admin-escalation` agent stops improvising a fetch +
inline python3 and keeps only judgment (level determination, alert composition).
The weekly habit report moves entirely off the LLM into a systemd-timer driver
(`scripts/habits/weekly_report_driver.py`) that runs the existing
`query_active_habits_weekly --output text` helper and delivers via
`openclaw message send --channel whatsapp`, retiring the openclaw
`habits-weekly-report` cron. Both paths read Vikunja scope selectors (excluded
projects, habit identity) from a shared config (`scripts/common/vikunja_scope.py`)
so the #714 reorganization is a config swap. Both jobs remain observable to the
#722 canary.

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; repo targets 3.12+)
**Primary Dependencies**: stdlib only for helpers; `scripts.common.vikunja_client.VikunjaClient` (stdlib HTTP wrapper), `scripts.habits.query_active_habits_weekly` (existing report helper), the OpenClaw CLI (`openclaw message send`), systemd user timers
**Storage**: Vikunja REST API (task store); JSON freshness pointer (`last-tick.json`); existing JSONL escalation state (unchanged)
**Testing**: pytest with injected effects / a fake `VikunjaClient` and fake subprocess — no live network, no LLM (mirrors `scripts/canary` + `scripts/habits` test style)
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); systemd `--user` services run as `claude`
**Project Type**: single (Python helper/driver modules under `scripts/`)
**Performance Goals**: escalation enumeration ≤ 30 s/run; weekly driver ≤ 60 s end-to-end (NFR-001/002)
**Constraints**: deterministic (no LLM in the fixed paths); config-driven Vikunja scope (NFR-004); fail-safe + truthful delivery (FR-006); AGENTS.md + systemd units are audited surfaces → rebaseline (C-003/C-004)
**Scale/Scope**: 2 crons, single user, task volumes in the tens–low hundreds; `/tasks/all` paginated at `per_page=50`

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Directive 6 (deterministic → helpers)**: This is the mission's core — mechanize the deterministic enumeration + weekly-report paths into tested helpers/drivers; reserve the LLM for genuine judgment only. **PASS (advances the directive).**
- **DIRECTIVE_024 (Locality of Change)**: Changes stay within `scripts/escalation`, `scripts/habits`, `scripts/common`, `scripts/office2`, the escalation agent prompt, and the service inventory. No unrelated surfaces. **PASS.**
- **DIRECTIVE_001 / 031 (Architectural integrity / context-aware)**: The shared scope config is an explicit translation boundary between the escalation/habits logic and the concrete Vikunja taxonomy — decoupling from #714 rather than implicit coupling. **PASS.**
- **DIRECTIVE_010 (Spec fidelity)**: FR/NFR/C mapped to ICs below. **PASS.**
- **Change-risk taxonomy / Rebaseline obligation**: Tier 3 (logic + a new user timer). AGENTS.md and `scripts/office2/*.service|*.timer` are hashed audited surfaces (auto-rebaseline on repo-file signal); the openclaw-cron removal has **no** repo-file signal → declared via manifest `expected_baselines`. **ACKNOWLEDGED (C-003/C-004).**

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this mission)

```
kitty-specs/deterministic-cron-hardening-01KXA4PX/
├── plan.md              # This file
├── research.md          # Phase 0 output (live-probe findings + decisions)
├── data-model.md        # Phase 1 output (entities)
├── quickstart.md        # Phase 1 output (verification walkthrough)
├── contracts/           # Phase 1 output (scope-config + driver + enumerate contracts)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/
├── common/
│   └── vikunja_scope.py            # NEW: shared Vikunja scope config (excluded projects, habit selector) + accessors
├── escalation/
│   └── enumerate_candidates.py     # NEW: deterministic candidate enumeration (/tasks/all → client-side §1 filter → JSON)
├── habits/
│   ├── query_active_habits_weekly.py  # MODIFIED: read habit project id from vikunja_scope (was hardcoded HABITS_PROJECT_ID=13)
│   └── weekly_report_driver.py     # NEW: deterministic driver (run helper → openclaw message send → freshness pointer)
├── office2/
│   ├── felix-habits-weekly.service # NEW: systemd user unit (ExecStart = python3 -m scripts.habits.weekly_report_driver)
│   ├── felix-habits-weekly.timer   # NEW: systemd user timer (Monday 06:00 America/New_York)
│   └── felix-habits-weekly-onfailure.service  # NEW: OnFailure ntfy shim (mirror felix-canary)
└── deploy/
    └── deploy-habits-weekly-driver.py  # NEW: deploy entrypoint (install units, verify-before-enable, retire openclaw cron, report via #701 bus)

scripts/openclaw/agents/felix-admin-escalation/AGENTS.md  # MODIFIED: Step 2 → call enumerate_candidates (audited surface)
scripts/openclaw/skills/escalation/SKILL.md               # MODIFIED: §1 references the helper as the enumeration mechanism
docs/design/architecture/data/service-inventory.json      # MODIFIED: add felix-habits-weekly service (tick-signal-file); drop habits-weekly-report from habit-checkin crons
deploys/queued/00NN-habits-weekly-driver.yaml             # NEW: deploy manifest (expected_baselines: the drifted openclaw-cron baseline)

tests/common/test_vikunja_scope.py            # NEW
tests/escalation/test_enumerate_candidates.py # NEW
tests/habits/test_weekly_report_driver.py     # NEW
```

**Structure Decision**: Single-project Python. New deterministic modules live beside their existing peers (`scripts/escalation`, `scripts/habits`, `scripts/common`), the systemd units beside the other office2 units (`scripts/office2`), and the deploy entrypoint beside the other deploy scripts — consistent with the felix-canary / felix-health-check precedents.

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Shared Vikunja scope config

- **Purpose**: Externalize the Vikunja selectors (excluded project IDs for escalation; habit identity for the habit helpers) into one module so the #714 reorg is a config edit, not a code change.
- **Relevant requirements**: FR-008, NFR-004, C-006.
- **Affected surfaces**: `scripts/common/vikunja_scope.py` (NEW); refactor `scripts/habits/query_active_habits_weekly.py` to read the habit project id from it (was `HABITS_PROJECT_ID = 13`).
- **Sequencing/depends-on**: none (foundation for IC-02 + IC-03).
- **Risks**: Must not regress the working weekly helper. Habit selector shaped for a future label form (`{kind: "project_id"|"label", value}`) even though today it is `project_id: 13`. Morning-checkin adoption of the config is optional/low-cost — note but do not force (keep locality).

### IC-02 — Escalation candidate-enumeration helper + prompt rewrite

- **Purpose**: Replace the agent's improvised `/projects/-4/tasks` fetch + inline python3 with a deterministic helper.
- **Relevant requirements**: FR-001, FR-002, FR-003; C-001, C-002.
- **Affected surfaces**: `scripts/escalation/enumerate_candidates.py` (NEW — paginate `/tasks/all` per_page=50, client-side filter per §1: `done=false`, `priority>=2`, `project_id` not in scope-excluded, overdue OR due-today-with-`priority>=3`, drop null-due sentinel + snoozed/dismissed handled downstream by derive_state); `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` Step 2 (audited surface); `scripts/openclaw/skills/escalation/SKILL.md` §1.
- **Sequencing/depends-on**: IC-01 (reads excluded projects from scope config).
- **Risks**: client-side filter must be faithful to §1 (tested against fixtures); `/tasks/all` pagination stop condition (empty batch, not `len<100`); AGENTS.md edit triggers rebaseline; keep the agent's downstream `derive_state`/`record_completion` flow intact (enumeration only replaces Step 2).

### IC-03 — Weekly-report deterministic driver

- **Purpose**: Produce + deliver the weekly report with no LLM turn.
- **Relevant requirements**: FR-004, FR-005, FR-006, FR-007.
- **Affected surfaces**: `scripts/habits/weekly_report_driver.py` (NEW — run `query_active_habits_weekly --output text`, prefix the fixed attribution line, deliver via `openclaw message send --channel whatsapp --target <E.164> --message <body> --json`, confirm delivery from the JSON result, write a `last-tick.json` freshness pointer); `scripts/office2/felix-habits-weekly.{service,timer,onfailure}`.
- **Sequencing/depends-on**: IC-01 (the weekly helper it wraps reads the scope config).
- **Risks**: truthful delivery (FR-006) — only stamp success when the send result confirms delivery; the attribution line preserves observed-mode identity; retiring the openclaw cron is a deploy step (IC-04), not a code step; weekly cadence means the freshness pointer's `max_age_seconds` is ~8 days.

### IC-04 — Observability + deploy

- **Purpose**: Keep both jobs canary-observable and deploy safely with correct rebaseline.
- **Relevant requirements**: FR-009, FR-010; C-003, C-004.
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json` (add `felix-habits-weekly` as a `tick-signal-file` freshness service, `max_age_seconds` ≈ 8 days; remove `habits-weekly-report` from `habit-checkin`'s `openclaw-cron-state` `crons` list); `scripts/deploy/deploy-habits-weekly-driver.py` (install units + daemon-reload + verify-before-enable gate + `openclaw cron rm` the retired cron + report via #701 bus); `deploys/queued/00NN-habits-weekly-driver.yaml` (`expected_baselines` naming the drifted openclaw-cron baseline, since the cron removal has no repo-file signal).
- **Sequencing/depends-on**: IC-02, IC-03 (deploys their outputs).
- **Risks**: verify-before-enable must run the real unit once and assert a fresh `last-tick.json` (mirror felix-canary #711/#703 lesson — don't trust dry-run); systemd-unit changes auto-rebaseline (repo-file signal); the openclaw-cron removal needs `expected_baselines`; escalation-daily stays an openclaw-cron (no service-inventory change — the fix just makes its runs succeed).

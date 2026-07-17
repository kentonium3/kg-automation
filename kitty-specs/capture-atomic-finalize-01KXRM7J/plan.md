# Implementation Plan: Atomic Capture Finalize Across Route Kinds

**Branch**: `fix/capture-atomic-finalize` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/capture-atomic-finalize-01KXRM7J/spec.md`
**Issue**: kentonium3/kg-automation#746

## Summary

Generalize #737's calendar-only atomic `route_calendar_event --finalize` into a
single generic finalize mechanism that covers **every** inbox route kind. The
mechanism performs route → verify artifact → write routing-log entry →
mark-processed as one indivisible, fail-loud operation, and it becomes the
**only** path by which a note reaches `status: processed`. The capture agent's
standalone `mark_processed` step is removed from its standing orders. A new
health rail flags any `processed` note that lacks a routing-log entry, making the
silent-loss class visible.

## Technical Context

**Language/Version**: Python 3.10+ (office2 is python3-only; helpers invoked as `python3 -m scripts.inbox.<helper>`)
**Primary Dependencies**: stdlib only for the finalize/route/log helpers (NFR: no requests/httpx/pydantic/PyYAML/frontmatter); the existing `scripts.common.vikunja_client.VikunjaClient` (stdlib) for Vikunja verification; the calendar helper runs in its dedicated office2 venv via subprocess (unchanged from #737)
**Storage**: append-only JSONL routing log at `/data/services/openclaw/state/inbox-routing.jsonl`; inbox notes (markdown + frontmatter) in the Obsidian vault `01-Inbox/` / `02-Inbox-Processed/`
**Testing**: pytest; per-kind finalize unit tests (success / route-failure / verify-failure / idempotent-reprocess) with mocked external calls; health-rail unit tests; calendar regression tests remain green (NFR-003)
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); authored on macOS
**Project Type**: single project (Python helper library + OpenClaw agent prompt)
**Performance Goals**: bounded per-note latency — every external call carries an explicit subprocess/timeout (reuse #737's 90s create / 30s mark_processed pattern); no unbounded hangs within the 600s openclaw cron turn limit
**Constraints**: Tier 3 (Python helpers + agent prompt). Inbox invariant: never delete/move the original note; frontmatter-only writes. Privacy: never touch `04-Growth/_private/`. Routing log is the dedup substrate and must be written inside the atomic unit.
**Scale/Scope**: 5 route kinds + 1 no-route disposition; one new dispatcher module; one routing-log schema extension; one health-rail extension; one agent-prompt rewrite; deploy to a single office2 host.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Charter directive | Status | Notes |
|---|---|---|
| DIRECTIVE_001 Architectural Integrity / DIRECTIVE_024 Locality of Change | PASS | One finalize skeleton owns the atomic sequence; per-kind route+verify functions are small, isolated seams. Blast radius bounded to `scripts/inbox/` + capture AGENTS.md. |
| DIRECTIVE_034 Test-First | PASS | Each kind's finalize gets success/failure/idempotent tests before implementation; calendar regression tests are the fold's safety net. |
| DIR-001/002 office2 python3-only, Linux | PASS | `-m` invocation form; no bare `python`. |
| DIR-004/005 Deploy discipline | PASS (planned) | Helper changes deploy via office2 checkout self-pull; AGENTS.md via `agent-prompt-sync`; a `deploys/queued/` manifest is added if any office2-side apply step is required beyond the self-pull (see Deploy Plan). |
| DIR-011 Privacy hard boundary | PASS | mark_processed's `_private/` refusal (exit 3) is preserved and is the reason finalize keeps calling mark_processed as a **subprocess** (guards live in `main()`). |
| DIR-014 Documentation sync | PASS (planned) | AGENTS.md(+tmpl), runbook, service-inventory health-check entry, INDEX/roadmap as applicable (FR-014). |
| Rebaseline obligation (#557/#621) | Expected **not required** | Agent AGENTS.md is not a hashed audited surface (#621); helper scripts under `scripts/inbox/` are not in `audited-surfaces.json`. Confirm at merge; record `Rebaseline: not required — <reason>`. |

No violations → Complexity Tracking is empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/capture-atomic-finalize-01KXRM7J/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (finalize CLI + result shapes, health-rail shape)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/inbox/
├── route_and_finalize.py        # NEW: generic dispatcher — the ONE command capture runs per route
├── route_calendar_event.py      # MODIFIED: calendar route+verify folded into the generic finalize (calendar create/verify internals preserved)
├── route_someday.py             # route helper (reused; wrapped by finalize)
├── route_journal_entry.py       # route helper (reused; wrapped by finalize)
├── mark_processed.py            # unchanged; still the sole status:processed writer, invoked as a subprocess by finalize
├── routing_log.py               # MODIFIED: `kind` enum grows (someday/journal/vikunja_task/github_issue/empty); reader unchanged (keys on filename)
├── append_routing_entry.py      # MODIFIED or retired-from-agent-use: finalize writes the log internally; standalone CLI kept only if still needed by non-capture callers
└── prescan.py                   # MODIFIED: new health rail — `processed` note with no routing-log entry

scripts/openclaw/agents/main/felix-file-issue.py   # github_issue route (reused; wrapped by finalize)

scripts/openclaw/agents/felix-admin-capture/
├── AGENTS.md                    # MODIFIED: single-finalize-command-per-route; remove standalone Step 5b/5c
├── AGENTS.md.tmpl               # MODIFIED: source of truth mirror
└── TOOLS.md(.tmpl)              # MODIFIED if the toolkit surface changes (remove standalone mark_processed)

tests/inbox/                     # per-kind finalize + health-rail tests
deploys/queued/<name>.yaml       # deploy manifest if an office2 apply step is needed
```

**Structure Decision**: Single Python helper library under `scripts/inbox/`, matching the existing inbox toolkit. The new `route_and_finalize.py` dispatcher owns the atomic finalize skeleton (mirroring `route_calendar_event._run_finalize`); each route kind contributes a small `route+verify` function. Calendar folds in by having the dispatcher call the existing calendar create/verify path — no divergent finalize implementation.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

### IC-01 — Generic finalize skeleton + dispatcher

- **Purpose**: One atomic, fail-loud `route_and_finalize(kind, payload, source_path)` operation that performs route → verify → routing-log → mark-processed, deriving its exit code from the OUTCOME (never from the always-0 route step), mirroring the proven `route_calendar_event._run_finalize` shape.
- **Relevant requirements**: FR-001, FR-003, FR-004, FR-009, FR-011; NFR-001, NFR-002, NFR-004, NFR-005
- **Affected surfaces**: `scripts/inbox/route_and_finalize.py` (new), `scripts/inbox/mark_processed.py` (subprocess call site), `scripts/inbox/routing_log.py`
- **Sequencing/depends-on**: none (foundation)
- **Risks**: Ordering correctness — routing-log append MUST come after mark_processed (prescan dedups on routing-log filename; log-before-mark can strand a note). Idempotency via `RoutingLogReader.has()`. mark_processed MUST stay a subprocess (symlink/`_private`/inbox-root guards live in `main()`, and stdout isolation).

### IC-02 — Per-kind route + verify adapters

- **Purpose**: For each kind (someday, journal, vikunja_task incl. tasker-delegated id, github_issue, calendar folded in, empty no-route) provide the route call + artifact-verification predicate the skeleton consumes.
- **Relevant requirements**: FR-002, FR-003, FR-006, FR-007, FR-012
- **Affected surfaces**: `route_and_finalize.py` (per-kind adapters), `route_someday.py`, `route_journal_entry.py`, `route_calendar_event.py`, `felix-file-issue.py`, `vikunja_client.py` (verify a task id resolves)
- **Sequencing/depends-on**: IC-01
- **Risks**: The tasker-delegated `vikunja_task` path supplies an externally-created id — finalize must verify it exists (not create), then log+mark. Calendar fold must preserve #737's `needs_clarification`/`error` behavior exactly (NFR-003). `empty` disposition writes a routing-log entry so the health-rail invariant is total.

### IC-03 — Routing-log schema evolution

- **Purpose**: Extend the routing-log `kind` vocabulary to the full kind set and ensure every finalize records kind + destination + artifact id; keep old rows readable.
- **Relevant requirements**: FR-009; C-005
- **Affected surfaces**: `routing_log.py` (`RoutingEntry.kind` values), `append_routing_entry.py` (`--kind` choices) if retained
- **Sequencing/depends-on**: IC-01
- **Risks**: Reader keys only on `filename`, so schema growth is backward-compatible; ensure writers populate `destination` per kind.

### IC-04 — Health rail: processed-without-routing-log

- **Purpose**: Add a defensive scan that flags any note with `status: processed` (in `01-Inbox/` and `02-Inbox-Processed/`) whose filename is absent from the routing log — the exact signature that hid the loss.
- **Relevant requirements**: FR-010; NFR-001
- **Affected surfaces**: `scripts/inbox/prescan.py` (`scan_archive_anomalies` sibling / new `ArchiveAnomaly` classification `processed-without-routing-log`), cross-referencing `RoutingLogReader`
- **Sequencing/depends-on**: IC-03 (empty disposition must log, else false positives)
- **Risks**: Must not false-positive on legitimately empty notes (they now log kind=empty) or `needs-review` notes (not `processed`). Latency: reuse the `ARCHIVE_SCAN_CAP` bound.

### IC-05 — Agent standing-orders rewrite + toolkit removal

- **Purpose**: Rewrite `felix-admin-capture` AGENTS.md to the single-finalize-command-per-route model; remove the standalone `mark_processed` / `append_routing_entry` steps so the agent can no longer stamp `processed` on its own.
- **Relevant requirements**: FR-005, FR-013
- **Affected surfaces**: `felix-admin-capture/AGENTS.md`(+`.tmpl`), `TOOLS.md`(+`.tmpl`)
- **Sequencing/depends-on**: IC-01, IC-02 (the command must exist before the prompt points at it)
- **Risks**: AGENTS.md 12K byte cap (`test_agents_md_size.py`) — the rewrite likely *reduces* size (collapsing 5b/5c per-kind into one command). Preserve Output-Discipline hard rules and the `needs-review` direct-edit exception. Keep `.tmpl` mirror in parity.

### IC-06 — Documentation sync + deploy

- **Purpose**: Synchronize docs (DIR-014) and deploy to office2 through the manifest discipline / agent-prompt-sync.
- **Relevant requirements**: FR-014; C-002
- **Affected surfaces**: capture runbook, `docs/design/architecture/data/service-inventory.json` (+ md view) for the new health-check, `docs/INDEX.md`/roadmap as applicable, `deploys/queued/<name>.yaml`
- **Sequencing/depends-on**: IC-01..IC-05
- **Risks**: Deploy split — helpers land via office2 checkout self-pull; AGENTS.md via `agent-prompt-sync` (slug `felix-admin-capture` deploys to `/data/services/openclaw/inbox-agent/`, per [[reference_office2_agent_deploy_paths]]). Confirm rebaseline not-required at merge.

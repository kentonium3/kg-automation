# Implementation Plan: Atomic Capture Finalize Across Route Kinds

**Branch**: `fix/capture-atomic-finalize` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/capture-atomic-finalize-01KXRM7J/spec.md`
**Issue**: kentonium3/kg-automation#746

## Summary

Generalize #737's calendar-only atomic `route_calendar_event --finalize` into a
**note-level finalize transaction** covering every inbox route kind. Because
`classify_content` splits a note into multiple blocks that can route to different
kinds, and `status: processed` is note-level, finalize routes **all** blocks →
verifies **all** artifacts → writes a **per-block** routing-log entry → marks the
note processed **once**, as one indivisible, fail-loud, retry-safe operation. It
becomes the **only** path to `status: processed`; the agent's standalone
`mark_processed`/`append_routing_entry` are removed. A health rail flags any
`processed` note lacking a routing-log entry and is surfaced in the agent's IDLE
gate so the alarm reaches Kent.

**Post-plan Codex review (2026-07-17) folded**: 12 findings (6H/6M) reshaped the
design from per-route to note-level (findings 1–2), added an explicit log/mark
state machine (3, 11-cal), per-block idempotency keys + per-kind
retry-safety (4, 5), agent-hop provenance for tasker + github (6, 7), empty-note
body validation (8), prescan `needs-review` terminal + health-rail-in-IDLE-gate
(9, 11). Finding 10 (pending-calendar-clarification surfacing) deferred to #740
(Kent's scope call).

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

### IC-01 — Note-level finalize transaction + state machine

- **Purpose**: The `route_and_finalize` note-level operation — consume the agent's per-block routing plan, route each block, verify each artifact, write each block's routing-log entry, then mark the note processed ONCE, only after all blocks are logged. Exit code from the OUTCOME. Resolves the log/mark ordering with an explicit state machine (log-per-block-before-mark; re-run reconciles from the log).
- **Relevant requirements**: FR-001, FR-003, FR-004, FR-011; NFR-001, NFR-002, NFR-005
- **Affected surfaces**: `scripts/inbox/route_and_finalize.py` (new), `mark_processed.py` (subprocess call site), `routing_log.py`, `classify_content.py` (block plan shape)
- **Sequencing/depends-on**: none (foundation)
- **Risks**: Partial-failure semantics across blocks (one block succeeds, another fails → note stays unprocessed, succeeded block not re-created next tick). mark_processed MUST stay a subprocess (symlink/`_private`/inbox-root guards live in `main()` + stdout isolation). The note-level mark happens exactly once after all blocks logged.

### IC-02 — Per-block routing-log keys + per-kind idempotency

- **Purpose**: Key routing-log entries on **note filename + block index + block content hash** (findings 2); make each kind's side effect idempotent/retry-safe before performing it (findings 4, 5): calendar source-path key; someday/vikunja_task block-key precheck; journal per-block sentinel + verify-before-append; github block-key + issue verify.
- **Relevant requirements**: FR-009, FR-010; NFR-004
- **Affected surfaces**: `routing_log.py` (`RoutingEntry` gains block index/hash + kind vocabulary), `route_someday.py`, `route_journal_entry.py`, `route_calendar_event.py`, `felix-file-issue.py`
- **Sequencing/depends-on**: IC-01
- **Risks**: Block-hash stability across ticks for an unchanged note; reader stays backward-compatible (old rows lack block fields — dedup falls back to filename for legacy rows). Journal sentinel must be invisible/non-disruptive in the rendered note.

### IC-03 — Per-kind route + verify adapters (incl. agent-hop provenance)

- **Purpose**: For each kind provide route call + artifact verification: someday/vikunja_task (task id resolves), journal (file/section exists), github_issue (issue number non-null + verifiable), calendar (folded #737 create/verify), empty (body-genuinely-empty validation). Tasker-delegated + github are agent-hops: verify **provenance** (task belongs to this note; issue number returned), findings 6/7.
- **Relevant requirements**: FR-002, FR-003, FR-006, FR-007, FR-012, FR-015
- **Affected surfaces**: `route_and_finalize.py` (adapters), the route helpers, `vikunja_client.py` (fetch+provenance), `felix-file-issue.py` (null-issue handling)
- **Sequencing/depends-on**: IC-01
- **Risks**: Calendar fold must preserve #737 create/needs_clarification/error behavior (NFR-003); the `finalized`+`routing_logged:false` leniency is intentionally removed (FR-015) — update those tests. `empty` must refuse a non-empty body (finding 8, silent-loss escape hatch). Tasker provenance depends on the `Source:` footer being present.

### IC-04 — Health rail + prescan terminal-state hygiene

- **Purpose**: Add the `processed-without-routing-log` anomaly to `prescan` (scan `01-Inbox/` + `02-Inbox-Processed/`, cross-ref `RoutingLogReader`); classify inbox `needs-review` as terminal (excluded from `unprocessed_paths`, finding 9); shift prescan's note dedup from routing-log-filename to note `status`.
- **Relevant requirements**: FR-008, FR-013; NFR-001
- **Affected surfaces**: `scripts/inbox/prescan.py` (`scan_archive_anomalies` + `classify_file`/`unprocessed_paths` logic)
- **Sequencing/depends-on**: IC-02 (empty/block logging must exist so the rail has no false positives)
- **Risks**: Must not false-positive on `empty`-logged notes or `needs-review`. Latency via `ARCHIVE_SCAN_CAP`. The dedup shift (log→status) must not reintroduce reprocessing of a note whose blocks are mid-flight — reconciliation is the block-keyed idempotency in IC-02.

### IC-05 — Agent standing-orders rewrite (note-level) + IDLE-gate surfacing

- **Purpose**: Rewrite `felix-admin-capture` AGENTS.md to: classify blocks → assemble routing plan → invoke ONE note-level finalize; remove standalone `mark_processed`/`append_routing_entry` (finding 5-set, FR-005/FR-016). Update Step 1 IDLE gate to block IDLE and report `archive_anomalies` incl. `processed-without-routing-log` (finding 11, FR-014).
- **Relevant requirements**: FR-005, FR-014, FR-016; C-005
- **Affected surfaces**: `felix-admin-capture/AGENTS.md`(+`.tmpl`), `TOOLS.md`(+`.tmpl`)
- **Sequencing/depends-on**: IC-01..IC-04
- **Risks**: AGENTS.md 12K byte cap (`test_agents_md_size.py`) — the note-level single-command model should *reduce* size (collapsing per-kind 5b/5c). Preserve Output-Discipline hard rules + the `needs-review` direct-edit exception (the only sanctioned non-finalize frontmatter write). `.tmpl` parity.

### IC-06 — Documentation sync + deploy

- **Purpose**: Synchronize docs (DIR-014) and deploy to office2.
- **Relevant requirements**: FR-017; C-002
- **Affected surfaces**: capture runbook, `docs/design/architecture/data/service-inventory.json` (+ md view) for the new health-check, `docs/INDEX.md`/roadmap as applicable, `deploys/queued/<name>.yaml` if needed
- **Sequencing/depends-on**: IC-01..IC-05
- **Risks**: Deploy split — helpers via office2 checkout self-pull; AGENTS.md via `agent-prompt-sync` (slug `felix-admin-capture` → `/data/services/openclaw/inbox-agent/`, [[reference_office2_agent_deploy_paths]]). Confirm rebaseline not-required at merge (#621).

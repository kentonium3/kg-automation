# Tasks: Atomic Capture Finalize Across Route Kinds

**Mission**: capture-atomic-finalize-01KXRM7J | **Branch**: `fix/capture-atomic-finalize`
**Issue**: kentonium3/kg-automation#746

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Extend `RoutingEntry` with `block_index` + `block_hash` (Optional, backward-compat) | WP01 | | [D] |
| T002 | Grow `kind` vocabulary (someday/journal/vikunja_task/github_issue/empty) + `destination` population | WP01 | [D] |
| T003 | Block-key helpers: compute `block_hash`; `has_block()`; legacy filename fallback | WP01 | | [D] |
| T004 | Update `append_routing_entry` CLI (`--kind` choices + block args) | WP01 | [D] |
| T005 | Tests: schema round-trip, block-key dedup, legacy-row fallback | WP01 | | [D] |
| T006 | `route_and_finalize.py` skeleton: plan parse, per-block loop, note-level mark-once (subprocess), exit-from-outcome, result JSON, `--dry-run` | WP02 | |
| T007 | Finalize state machine: log-per-block-before-mark; reconcile-from-log on re-run | WP02 | |
| T008 | someday + vikunja_task adapters (in-process + tasker-delegated id; provenance verify; block-key idempotency) | WP02 | |
| T009 | journal adapter: per-block sentinel + verify-before-append (no duplicate section) | WP02 | |
| T010 | github_issue adapter: null issue# = failure; verify issue exists | WP02 | |
| T011 | calendar fold adapter: reuse create/verify; preserve #737 paths; remove `routing_logged:false` leniency | WP02 | |
| T012 | empty disposition: validate body genuinely empty; kind=empty log entry | WP02 | |
| T013 | Tests: per-kind success/route-fail/verify-fail + retry-no-double-create; multi-block all-or-nothing; calendar regression | WP02 | |
| T014 | prescan: `processed-without-routing-log` anomaly (scan 01-Inbox + 02-Inbox-Processed; exclude empty-logged + needs-review) | WP03 | | [D] |
| T015 | prescan: classify inbox `needs-review` terminal (exclude from `unprocessed_paths`); dedup shift log→status | WP03 | | [D] |
| T016 | Wire anomaly into `PrescanResult` for the Step 1 IDLE-gate to read | WP03 | | [D] |
| T017 | Tests: anomaly detection, no false-positive on empty/needs-review, needs-review not reprocessed | WP03 | | [D] |
| T018 | Rewrite AGENTS.md routing to note-level single-finalize; remove standalone Steps 5b/5c | WP04 | |
| T019 | Update Step 1 IDLE gate: block IDLE + report `archive_anomalies` incl processed-without-routing-log | WP04 | |
| T020 | Update TOOLS.md (remove standalone mark_processed/append_routing_entry); keep needs-review exception; mirror `.tmpl` | WP04 | |
| T021 | Verify AGENTS.md < 12K byte cap; `.tmpl` parity | WP04 | |
| T022 | Update inbox/capture runbook(s) to note-level finalize flow | WP05 | [P] |
| T023 | Add new health-check to service-inventory.json + md view; INDEX/roadmap as applicable | WP05 | [P] |
| T024 | deploys/queued manifest if needed; document deploy split + rebaseline-not-required | WP05 | |
| T025 | Update capability roadmap status (capture reliability) | WP05 | [P] |

## Work Packages

### WP01 — Routing-log block-keyed schema (foundation)
- **Goal**: Evolve the routing log so entries are keyed per block (filename+index+hash), grow the kind vocabulary, and keep legacy rows readable.
- **Priority**: P1 (foundation — everything depends on it)
- **Independent test**: `pytest tests/inbox/test_routing_log*.py` — new fields round-trip; `has_block` dedups; legacy rows fall back to filename.
- **Subtasks**: T001, T002, T003, T004, T005
- **Dependencies**: none
- **Prompt**: `tasks/WP01-routing-log-block-keys.md` (~250 lines)

### WP02 — Note-level finalize transaction + per-kind adapters (core)
- **Goal**: The `route_and_finalize` note-level transaction — route all blocks → verify all → log per block → mark once, fail-loud + retry-safe, covering every kind (calendar folded).
- **Priority**: P1 (the core fix)
- **Independent test**: `pytest tests/inbox/test_route_and_finalize*.py` + calendar regression green.
- **Subtasks**: T006, T007, T008, T009, T010, T011, T012, T013
- **Dependencies**: WP01
- **Prompt**: `tasks/WP02-note-level-finalize.md` (~600 lines)

### WP03 — Health rail + prescan terminal hygiene
- **Goal**: Detect `processed`-without-routing-log; make inbox `needs-review` terminal; shift note dedup to status.
- **Priority**: P1
- **Independent test**: `pytest tests/inbox/test_prescan*.py` — anomaly detected, no false positives, needs-review not reprocessed.
- **Subtasks**: T014, T015, T016, T017
- **Dependencies**: WP01
- **Prompt**: `tasks/WP03-health-rail-prescan.md` (~300 lines)

### WP04 — Agent standing-orders rewrite + IDLE-gate surfacing
- **Goal**: Capture AGENTS.md → note-level single-finalize; remove standalone mark_processed; IDLE gate surfaces anomalies.
- **Priority**: P1
- **Independent test**: `pytest tests/openclaw/...test_agents_md_size.py` green; AGENTS.md/`.tmpl` parity; manual read shows one-finalize-per-note flow.
- **Subtasks**: T018, T019, T020, T021
- **Dependencies**: WP02, WP03
- **Prompt**: `tasks/WP04-agent-standing-orders.md` (~300 lines)

### WP05 — Documentation sync + deploy
- **Goal**: Synchronize docs (DIR-014) and prepare the office2 deploy path.
- **Priority**: P2 (finalize/close-out)
- **Independent test**: `validate_docs` + `validate_architecture_data` green; manifest (if any) validates against schema.
- **Subtasks**: T022, T023, T024, T025
- **Dependencies**: WP01, WP02, WP03, WP04
- **Prompt**: `tasks/WP05-docs-deploy.md` (~250 lines)

## Dependency graph

```
WP01 ──┬──> WP02 ──┐
       └──> WP03 ──┴──> WP04 ──> WP05
```

WP02 and WP03 parallelize after WP01. WP04 needs WP02+WP03. WP05 last.

## MVP scope

WP01 + WP02 deliver the atomic guarantee (the silent-loss fix). WP03 makes violations
visible, WP04 makes the agent use the new mechanism, WP05 ships it. All five are required
to close #746.

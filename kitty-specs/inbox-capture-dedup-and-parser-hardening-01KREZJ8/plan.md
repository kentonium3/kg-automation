# Implementation Plan: Inbox Capture Dedup and Parser Hardening

**Branch**: `main` (direct-to-main per kg-automation convention) | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`

---

## Summary

Fix the P1-bug from #185 by giving `felix-admin-capture` a dedup mechanism that is **independent of frontmatter parseability** (the precise failure mode that caused the original loop). The fix has four coordinated parts:

1. **Routing log** at `~/second-brain/agents/state/inbox-routing.jsonl` — JSONL append-only, filename-keyed. Load-bearing dedup.
2. **Defensive parser** in `scripts/inbox/prescan.py` — detects 4 malformation classes (leading whitespace, UTF-8 BOM, missing closing `---`, invalid YAML); halts routing for affected notes.
3. **Batched "Inbox quality" GitHub issue** — surfaces parse-halts per cron run; deduped by title prefix.
4. **Obsidian callout marker** on malformed notes — visual identification; idempotent inject; auto-cleanup on next successful parse.

Plus the FR-011 belt: atomic `status: processed` frontmatter write after route (already roughly what the agent does today; this mission makes it FR-explicit).

---

## Technical Context

**Language/Version**: Python 3.12+ (stdlib only — `json`, `re`, `pathlib`, `subprocess`, `datetime`, `argparse`). Ubuntu 24.04 LTS on office2.
**Primary Dependencies**: stdlib + `PyYAML` (already a dependency of `prescan.py`).
**Storage**: `~/second-brain/agents/state/inbox-routing.jsonl` (new). Existing surfaces: notes in `~/second-brain/notes/01-Inbox/`, activity logs in `~/second-brain/agents/logs/`, GitHub issues, Vikunja tasks.
**Testing**: `pytest` for unit tests on the new helper modules + extended prescan classifier. Integration smoke via the canary procedure in `quickstart.md`.
**Target Platform**: office2 (Ubuntu 24.04 LTS), running as the `claude` user under OpenClaw cron.
**Project Type**: single-project (small Python helpers + agent workspace prompt updates + arch-doc edits).
**Performance Goals**: < 100ms overhead for routing-log lookup at 200-entry scale (NFR-001). Current scale is ~5 entries; budget has 40× headroom.
**Constraints**: no sudo (C-001); routing log NOT git-tracked (C-006); marker prefix `> [!error] felix-capture:` is a stable contract (C-005); arch docs updated in same change set (C-008).
**Scale/Scope**: ~5 inbox notes today; expected to remain under 50 in any foreseeable steady state (notes get processed within a few cron ticks and move out of `01-Inbox/`).

---

## Charter Check

The charter context resolver returned `mode: compact` with "Governance: unresolved" (charter references `pytest` and `python` tools not registered in the runtime tool registry — same state as prior missions this session). No charter-derived gates are enforceable. Action: skip Charter Check; re-evaluate post-design if a charter is registered before tasks.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/
├── plan.md                            # This file
├── spec.md                            # Requirements (specify phase)
├── meta.json                          # Mission metadata
├── research.md                        # Phase 0: plan-phase decisions (R-001..R-009)
├── data-model.md                      # Phase 1: entities, state model, transitions
├── quickstart.md                      # Phase 1: deploy + canary + day-2 ops
├── contracts/                         # Phase 1: helper-script + classifier interfaces
│   ├── routing-log.md
│   ├── prescan-classifier.md
│   ├── callout-marker.md
│   └── inbox-quality-issue-writer.md
├── checklists/
│   └── requirements.md                # Spec-quality validation
└── tasks/                             # Populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/inbox/
├── prescan.py                              # MODIFIED: extended classifier (R-004)
├── routing_log.py                          # NEW: routing-log helper module (R-002)
├── append_routing_entry.py                 # NEW: CLI wrapper for routing-log append (R-005)
├── inject_parse_error_marker.py            # NEW: callout marker injection (R-006)
├── strip_parse_error_marker.py             # NEW: callout marker auto-cleanup (R-006)
└── file_inbox_quality_issue.py             # NEW: batched issue writer (R-007)

scripts/openclaw/agents/felix-admin-capture/
└── AGENTS.md                               # MODIFIED: add routing-log + parse-failure workflow

tests/inbox/
├── conftest.py                             # NEW: sys.path bootstrap, fixture utilities
├── test_routing_log.py                     # NEW
├── test_prescan_parse_failure.py           # NEW (or extends existing test_prescan.py)
├── test_callout_marker.py                  # NEW
└── test_inbox_quality_issue_writer.py      # NEW

docs/design/architecture/
├── service-inventory.md                    # MODIFIED: note the new state file in felix-admin-capture entry
└── data/service-inventory.json             # MODIFIED: same; bump updated_by
```

**Structure Decision**: single-project layout. Helper scripts in `scripts/inbox/` neighborhood (matching `prescan.py`). Tests at `tests/inbox/`. No package layout — these are small, independently-invokable helpers each ≤200 lines, exactly the kg-automation script convention.

---

## Phases

### Phase 0 — Research (this command)

Output: `research.md` with 9 decisions and 3 deferred items.

- **A-003 resolved**: bug touched both the prescan read path AND the agent's frontmatter write path. Mission 027's fix was narrow; this mission widens the parser + adds orthogonal routing-log dedup.
- Implementation defaults documented (helper-script locations, marker shape, dedup search pattern, test strategy).

### Phase 1 — Design + contracts (this command)

Outputs: `data-model.md`, `contracts/{routing-log,prescan-classifier,callout-marker,inbox-quality-issue-writer}.md`, `quickstart.md`.

Data model formalizes the routing-log-as-source-of-truth design. Contracts have concrete input/output specs and test-coverage requirements for each new module.

### Phase 2 — Tasks (next command, `/spec-kitty.tasks`)

Not started by this command. Will decompose the work into WPs along these likely lines:

1. **Foundation**: routing-log module + tests; test fixtures for malformed notes.
2. **Defensive parser**: extend `prescan.py` classifier + tests.
3. **Helper scripts**: callout-marker inject + strip + tests.
4. **Inbox-quality issue writer**: helper + tests.
5. **AGENTS.md workflow update**: integrate the new helpers into the agent's prompt; add the routing-log write step after route; add the end-of-turn parse-failure handling.
6. **Architecture docs**: service-inventory.{json,md} + inbox-ops.md updates.
7. **Deploy + canary**: redeploy script for the agent workspace; canary procedure execution.

Exact WP boundaries are `/spec-kitty.tasks`' decision.

### Phase 3 — Implement + review + merge

Per the standard spec-kitty workflow. Acceptance gates per spec §6 (SC-001..SC-008).

---

## Complexity Tracking

No charter violations identified. No complexity exceptions claimed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *(none)* | — | — |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Defensive parser false-positives flag well-formed notes | low | medium (Kent sees noise; notes don't route until "fixed") | NFR-005 test coverage across the existing inbox + a representative sample of historical notes. Each malformation case has a tight detection rule documented in `contracts/prescan-classifier.md`. |
| Routing log file goes missing on disk | very low | high (one cron tick re-routes everything) | The log lives under `~/second-brain/agents/state/`, which is part of Restic's nightly snapshot. Worst case is 24h of routing history loss, which equates to at most a few dozen duplicates Kent can close manually. Documented in `quickstart.md` rollback. |
| Filename collision (Kent rename + re-use) creates false-positive dedup | very low | medium (a new note silently skipped) | Documented operational expectation in `quickstart.md` and operator runbook. Mitigation is "don't reuse filenames" — Obsidian's timestamp-based naming makes this naturally rare. |
| Marker injection breaks Obsidian sync or templater | very low | low (marker shape is standard Obsidian callout) | First-deploy canary verifies in real Obsidian environment. Rollback by removing marker is trivial. |
| Auto-cleanup strips a marker that was Kent-authored (false positive) | very low | low (Kent re-types if needed) | Prefix `felix-capture:` is namespaced and extremely unlikely to be Kent's own writing. Documented in spec §2 edge case. |
| New malformation pattern not in our enumeration slips through | low | medium (duplicates again — but the routing log catches this now) | The routing log is the **load-bearing** backstop: any pattern that makes prescan say "unprocessed" still produces only one route per note across time. The parser is the visibility layer; the routing log is correctness. |

---

## Branch contract (2nd of 2 mandatory restatements)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target for completed changes**: `main`
- **`branch_matches_target`**: true

Standard kg-automation direct-to-main workflow. No deviation.

---

## ⛔ Plan phase mandatory stop

Planning artefacts complete. Tasks generation requires `/spec-kitty.tasks` as a separate invocation.

Generated artefacts:

| File | Path |
|---|---|
| Plan | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/plan.md` |
| Research | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/research.md` |
| Data model | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/data-model.md` |
| Routing log contract | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/routing-log.md` |
| Prescan classifier contract | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/prescan-classifier.md` |
| Callout marker contract | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/callout-marker.md` |
| Inbox-quality issue contract | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/inbox-quality-issue-writer.md` |
| Quickstart | `kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/quickstart.md` |

Next: `/spec-kitty.tasks`.

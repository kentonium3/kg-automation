# Implementation Plan: Task-Intake Validation Loop

**Branch**: `feat/task-intake-validation-loop` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/task-intake-validation-loop-01KXS06W/spec.md`

## Summary

Build the Tier-1 task-intake validation loop the #714 reset deferred to this
epic: after each inbox-processing cron tick, a deterministic helper scans the
Vikunja Inbox for not-done, Tier-1-incomplete tasks (missing working project /
`f:` friction / `q:` Eisenhower); Felix sends one batched WhatsApp digest; Kent
replies in compact shorthand; a deterministic parser resolves the tokens via the
#748 `vikunja_refs` seam and applies project + labels + applicable Tier-2 through
the **kent token** (closing #750). Reply→digest correlation is **content-based**,
mirroring the habits `correlate_reply_to_checkin` pattern (WhatsApp quote-reply is
not plumbed to agents — see research R1). LLM is a narrow fallback for genuinely
unresolvable tokens only (Directive 6).

## Technical Context

**Language/Version**: Python 3.12+ (office2 is python3-only; helpers run as `python3 -m scripts.intake.<helper>`)
**Primary Dependencies**: `scripts.common.vikunja_refs` (#748 seam accessor, incl. `label_id(name, owner_token)`), `VikunjaClient`, the `scripts/vikunja/migrate_tasks.py` read-modify-write + kent-token primitives, the `scripts/habits/parse_morning_reply.py` correlation pattern, the `record_completion` ET-EOD date writer (#733)
**Storage**: JSON state artifacts under `/data/services/openclaw/state/intake/` (correlation record + per-tick observability), mirroring the habits state dir; Vikunja is the system of record for tasks/labels
**Testing**: pytest, deterministic, mocked Vikunja (no live-probe test modes — per standing guidance); fixtures under `tests/intake/`
**Target Platform**: office2 (Ubuntu 24.04 LTS); OpenClaw crons (`felix-admin-capture`) + main DM agent
**Project Type**: single project (Python helper scripts + agent prompts + docs)
**Performance Goals**: one WhatsApp digest per inbox tick regardless of task count (NFR-004); every external call timeout-bounded within the 600s cron turn (NFR-005)
**Constraints**: two-token model (kent writes / felix-bot reads, C-003); seam-only id resolution, no hardcoded ids (C-004); Vikunja POST partial-replace ⇒ read-modify-write (C-005); Directive-6 deterministic/LLM split (C-006); async reply on the DM lane bridged by the correlation record (C-007)
**Scale/Scope**: Kent's single-user Inbox (tens of tasks); 4 inbox ticks/day

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Architectural Integrity (DIRECTIVE_001) / Deterministic-work split (Directive 6, C-006):** PASS — scan/parse/resolve/apply are deterministic helpers; the LLM touches only the WhatsApp framing + a narrow unresolved-token fallback. Clear helper/agent boundary.
- **Decision Documentation (DIRECTIVE_003):** PASS — the reply-correlation decision (quote-reply falsified → content-based) is recorded in research R1 and the mission decisions index.
- **Specification Fidelity (DIRECTIVE_010):** PASS — plan traces every FR/NFR/C to an IC below.
- **Testing Standards / Quality Gates:** PASS — deterministic unit tests, mocked externals, no live-probe modes; drift gate (`vikunja_refs_validate.py`) stays green.
- **Change-Risk Taxonomy:** Tier 3 (Python helpers + agent prompts). **Rebaseline obligation:** NOT required — `audit.sh` hashes `openclaw.json`, not agent `AGENTS.md` (#621); no other audited surface changes. Recorded per R7.
- **Privacy:** N/A to Vikunja tasks (the `04-Growth/_private/` rule concerns the vault, not Vikunja); no vault reads.
- **Architecture doc obligation:** honored via IC-05 (service-inventory + data-flow + design-doc + runbook + INDEX/roadmap).

No violations → Complexity Tracking empty.

## Project Structure

### Documentation (this mission)
```
kitty-specs/task-intake-validation-loop-01KXS06W/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/helpers.contract.md
└── checklists/requirements.md
```

### Source Code (repository root)
```
scripts/
├── intake/                     # NEW deterministic helpers
│   ├── __init__.py
│   ├── scan_inbox.py           # IC-02
│   └── apply_reply.py          # IC-03
├── common/
│   ├── vikunja_refs.json       # IC-01: declare f:/q:/t:/loe: label ids
│   └── vikunja_refs.py         # (accessor already supports owner_token)
└── vikunja/migrate_tasks.py    # reused RMW + kent-token primitives (read-only ref)

tests/intake/                   # deterministic unit tests + fixtures

# Agent prompt deploy-sources (vault templates, synced via agent-prompt-sync):
#   felix-admin-capture AGENTS.md  (IC-04: run scan + emit digest)
#   main agent AGENTS.md / TOOLS.md (IC-04: correlate + invoke apply + confirm)

deploys/queued/<name>.yaml       # IC-05: state dir + kent-token assertion
docs/…                           # IC-05: design doc, architecture data, runbook, INDEX/roadmap
```

**Structure Decision:** Single project, matching the repo's `scripts/<domain>/`
helper convention. A new `scripts/intake/` domain owns the two helpers; the seam
stays in `scripts/common/`; agent behavior lives in the vault-template prompt
sources deployed via `agent-prompt-sync`. No `src/` layout — this repo is
script-first.

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Seam registry extension for the label taxonomy
- **Purpose:** declare the friction/Eisenhower/type/LOE label ids in the #748 seam so all resolution is fail-loud and drift-gated (no hardcoded ids).
- **Relevant requirements:** C-004, FR-006; data-model "Seam registry additions".
- **Affected surfaces:** `scripts/common/vikunja_refs.json`, `scripts/common/vikunja_refs_validate.py` (drift/AST gate), tests.
- **Sequencing/depends-on:** none (foundational; IC-02/IC-03 resolve against it).
- **Risks:** each label id must be reconciled against the **live** #715 set with exact evidence through the drift gate and `owner_token = "kent"` verified per label — **no approximate id ranges** in the final artifacts (Codex post-plan finding #11); the AST gate must accept the additions.

### IC-02 — Deterministic Inbox scan + Tier-1 classification + digest/observability artifacts
- **Purpose:** enumerate not-done Inbox tasks, classify Tier-1 completeness, write the correlation record + tick artifact, and render the numbered digest.
- **Relevant requirements:** FR-001, FR-002, FR-003, FR-008, FR-011, FR-014; NFR-001, NFR-004; SC-001, SC-003, SC-009.
- **Affected surfaces:** `scripts/intake/scan_inbox.py`, `tests/intake/`, the `/data/services/openclaw/state/intake/` artifacts.
- **Sequencing/depends-on:** IC-01.
- **Risks:** felix-bot read pagination (`GET /tasks/all` done-inclusive); injectable clock for determinism; **immutable per-`digest_id` correlation records + `latest` pointer + 48h expiry** (NOT overwrite-per-day — Codex finding #1); decomposition-pending tasks excluded from the intake count (finding #4).

### IC-03 — Shorthand parser + token resolution + apply via kent token
- **Purpose:** parse the compact-shorthand reply, resolve tokens (with alias table), and apply project + labels + applicable Tier-2 via the kent token, read-modify-write.
- **Relevant requirements:** FR-005, FR-006, FR-007, FR-009, FR-010, FR-012, FR-013; NFR-002, NFR-003, NFR-005; SC-002, SC-004, SC-005, SC-006, SC-007, SC-008.
- **Affected surfaces:** `scripts/intake/apply_reply.py`, `tests/intake/`; reuses `migrate_tasks.py` RMW/kent-token + `record_completion` ET-EOD.
- **Sequencing/depends-on:** IC-01, IC-02 (consumes the correlation record).
- **Risks:** kent-token-only writes (never felix-bot, the #750 defect); readback-diff non-clobber; **family-replace** for mutually-exclusive `q:`/`f:` (finding #2); **sparse-field** grammar (finding #3); `f:4` decomposition-pending terminal state (finding #4); per-line status set incl. `not_found`/`moved_conflict`/`already_done`/`access_denied` (finding #9); refined `noop` (finding #8); Tier-2 compatibility matrix + apply-time due prompt (findings #5/#6); the **constrained** `{line,token,position,canonical_name}` LLM-fallback re-resolved through the seam (finding #7); evidence-based correlation (finding #1).

### IC-04 — Agent wiring (capture + main prompts) and the LLM-fallback boundary
- **Purpose:** capture agent runs the scan after `route_and_finalize` and emits the digest; main DM agent recognizes an intake reply (content-based correlation), invokes the apply helper, and confirms results.
- **Relevant requirements:** FR-004, FR-006; research R1, R5, R6.
- **Affected surfaces:** `felix-admin-capture` `AGENTS.md`, main agent `AGENTS.md`/`TOOLS.md` (vault-template deploy sources).
- **Sequencing/depends-on:** IC-02, IC-03 (prompts invoke the helpers).
- **Risks:** the async DM-lane seam (the #737/#746 failure class) — keep agent logic thin, deterministic helpers own the work; AGENTS.md byte-cap headroom; content-based correlation must match habits semantics.

### IC-05 — Deploy manifest + documentation synchronization + #750 closure
- **Purpose:** provision the state dir + assert the kent-token secret; sync all doc surfaces; close #750.
- **Relevant requirements:** FR-015; C-002; research R7.
- **Affected surfaces:** `deploys/queued/<name>.yaml`; `docs/design/vikunja-configuration-design.md`, `docs/design/architecture/data/` (service-inventory + data-flow + md views), a new `docs/runbooks/intake-ops.md`, `docs/INDEX.md`, **`docs/DEVELOPER_PORTAL.md`** (per signal-to-doc-map when a doc surface is added — Codex finding #12), roadmap; the #750 closure note.
- **Sequencing/depends-on:** IC-01..IC-04.
- **Risks:** signal-to-doc-map coverage (INDEX/DEVELOPER_PORTAL routinely missed — #492); rebaseline recorded not-required (#621, confirmed by Codex finding #13).

## Complexity Tracking

*No Charter Check violations — none.*

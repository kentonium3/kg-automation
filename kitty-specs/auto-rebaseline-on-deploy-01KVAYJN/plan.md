# Implementation Plan: Auto-Rebaseline Security Baselines on Deploy

**Mission**: auto-rebaseline-on-deploy-01KVAYJN | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)
**Planning/coord branch**: `kitty/mission-auto-rebaseline-on-deploy-01KVAYJN` | **Merge target**: `main`
**Input**: Feature specification from `kitty-specs/auto-rebaseline-on-deploy-01KVAYJN/spec.md`

## Summary

felix-deployer gains a deferred-confirm rebaseline capability: its `git pull`
observes committed audited-surface changes; a pending token is reconciled on
later ticks by a read-only audit, and the security-monitor baselines are reset
automatically once the surface's drift is actually observed — no human on the
happy path. The audited-surface match logic is shared with the existing CI
reminder (one source of truth); failures, unexpected drift, and never-confirming
tokens raise ntfy alerts.

## Technical Context

**Language/Version**: Python 3.12 (matches existing `scripts/deploy/felix-deployer/` and `tooling/scripts/`)
**Primary Dependencies**: standard library (`subprocess`, `pathlib`, `json`, `datetime`), `PyYAML` (already used by `_tick.py`); no new third-party deps
**Storage**: filesystem state on office2 — pending token at `/data/services/felix-deployer/state/rebaseline-pending.json`; tick logs at `/data/services/felix-deployer/logs/<date>.jsonl`; baselines at `/data/services/security-monitor/baselines/`
**Testing**: pytest with subprocess/git/audit invocations mocked (mirrors existing `tests/deploy/` discipline); no live office2 in unit tests — live behavior covered by the post-merge integration canary (IC-04)
**Target Platform**: office2 (Ubuntu 24.04), runs as the `claude` user under the felix-deployer systemd oneshot+timer
**Project Type**: single project (Python automation in this repo)
**Performance Goals**: rebaseline + verification completes within one tick window (≤ 5 min, NFR-002)
**Constraints**: no sudo (claude user, `sg docker`, C-001); ships via `deploys/queued/` manifest (C-002); Tier 3 (C-003); reuse audited-surface matcher — no duplicate pattern list (NFR-001)
**Scale/Scope**: one applier process, ~14 baseline files, a registry of ~6 audited-surface classes

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity)** — PASS: the audited-surface matcher is extracted into one shared module; felix-deployer's rebaseline logic is a cohesive new unit with a clear boundary against `lib.apply`/`notify`.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS: design maps 1:1 to FR-001…FR-009.
- **DIRECTIVE_024 (Locality of Change)** — PASS: changes confined to `scripts/deploy/felix-deployer/`, a new shared matcher module, `audited-surfaces.json` (read-only consume), plus doc updates.
- **DIRECTIVE_033/034 (deterministic-work / helper split / test-first)** — PASS: path-intersection, audit-drift parsing, token read/modify/write, and baseline-count verification are deterministic helper logic with no LLM in the loop (this is unattended automation); tests are authored against the contract before implementation.
- **DIRECTIVE_031 (Context-Aware Design)** — PASS: the one load-bearing office2 assumption (audit.sh regenerate-vs-compare semantics) is flagged for a cheap live probe at the start of IC-02, not inferred.
- **Quality Gates — Integration gate ("WP05-equivalent")** — PASS via IC-04 / WP04 T017: this mission touches deployed services (felix-deployer + security-monitor on office2), so it requires an explicit integration verification exercising the real environment. A pre-merge live smoke is impossible (the code only goes live on the felix-deployer tick *after* merge), so the integration verification is an explicit **post-merge operator canary** (SC-001…SC-004) owned by IC-04, documented in `security-baseline-ops.md`, and recorded as the merge acceptance criterion. This matches the repo's established deferred-canary pattern (mission #185). Unit tests + dry-run are necessary but not sufficient; the canary is the sufficient gate.
- **Testing Standards — integration before for_review** — PASS: WP03 wires the engine into `run_tick()` as a live caller (no dead code); the canary (IC-04) is the live-environment verification.
- **Change-Risk Taxonomy** — Tier 3 (logic/workflow). The rebaseline it invokes resets security baselines, so the trigger is gated to fire only on a clean confirmed-drift signal (`D⊆E, D≠∅`).
- **Rebaseline Obligation (#557)** — this mission AMENDS that charter section: automation becomes the happy path; manual reset becomes the out-of-band exception (C-004).

No violations to justify in Complexity Tracking.

## Project Structure

### Documentation (this mission)

```
kitty-specs/auto-rebaseline-on-deploy-01KVAYJN/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── rebaseline-lifecycle-v1.md
```

### Source Code (repository root)

```
tooling/scripts/
├── audited_surfaces.py             # NEW: shared matcher (extracted from check_audited_surface_drift.py)
└── check_audited_surface_drift.py  # MODIFIED: imports the shared matcher (no behavior change)

scripts/deploy/felix-deployer/
├── _tick.py                        # MODIFIED: after pull, set pending token; reconcile pending each tick
├── rebaseline.py                   # NEW: pending-token model + audit-drift confirm + rebaseline + verify
└── notify.py                       # MODIFIED: add rebaseline-event ntfy dispatch (failure / unexpected-drift / stale)

deploys/queued/
└── 00NN-felix-deployer-auto-rebaseline.yaml  # NEW: ships the code update to office2 (number assigned at tasks time)

tests/deploy/
├── test_rebaseline.py              # NEW: pending lifecycle, confirm/clean/unexpected branches, failure paths
├── test_audited_surfaces.py        # NEW: shared-matcher parity with CI script
└── test_tick_rebaseline.py         # NEW: tick integration, no-crash discipline
```

**Structure Decision**: Single-project Python. New logic lives in a dedicated
`scripts/deploy/felix-deployer/rebaseline.py` so `_tick.py` stays a thin
orchestrator; the matcher is shared via `tooling/scripts/audited_surfaces.py`.

## Implementation Concern Map

### IC-01 — Shared audited-surface matcher
- **Purpose**: One importable matcher consumed by both the CI reminder and felix-deployer, so deploy-time and repo-time checks cannot diverge.
- **Relevant requirements**: NFR-001, FR-001, FR-008.
- **Affected surfaces**: `tooling/scripts/audited_surfaces.py` (new), `tooling/scripts/check_audited_surface_drift.py` (refactor to import), `tests/deploy/test_audited_surfaces.py`.
- **Sequencing/depends-on**: none (foundational).
- **Risks**: keep the CI script's CLI + exit semantics byte-stable; the `**` glob over-match approximation must move verbatim.

### IC-02 — Pending-token lifecycle + audit-confirmed rebaseline
- **Purpose**: The deferred-confirm engine — set/read/clear the pending token, run the read-only audit, classify drift (expected → rebaseline; clean → clear; unexpected → alert), regenerate baselines, and verify health.
- **Relevant requirements**: FR-002, FR-004, FR-005, FR-007, FR-008, FR-009.
- **Affected surfaces**: `scripts/deploy/felix-deployer/rebaseline.py` (new), `scripts/deploy/felix-deployer/_tick.py` (pull-range intersect + reconcile call), `tests/deploy/test_rebaseline.py`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: correctly distinguishing expected vs unexpected drift; atomic token writes; the audit-with-baselines (compare) vs `rm + audit` (regenerate) invocation distinction — **probe on office2 at IC-02 start** (DIRECTIVE_031), tests mock it.

### IC-03 — Tick integration + observability stamping + ntfy alerts
- **Purpose**: Wire observe+reconcile into `run_tick()`; record the rebaseline outcome (completed / not-required / failed / cleared_clean / unexpected_drift / stale) on the tick log + deploy record; emit exactly-one ntfy alert on failure, unexpected drift, or stale token. Absolute no-crash discipline.
- **Relevant requirements**: FR-003, FR-006, FR-009, NFR-002, NFR-004.
- **Affected surfaces**: `scripts/deploy/felix-deployer/_tick.py`, `scripts/deploy/felix-deployer/notify.py` (new dispatch), `tests/deploy/test_tick_rebaseline.py`.
- **Sequencing/depends-on**: IC-02.
- **Risks**: dedupe alerts (one per event per token, not per tick); never crash the tick on dispatch error (reuse existing wrap); keep within the tick window (NFR-002) — add an explicit timing/budget assertion.

### IC-04 — Deploy manifest + documentation amendment + post-merge integration canary
- **Purpose**: Ship the change to office2 via the manifest pipeline; update CLAUDE.md + charter so automation is the documented happy path; and **own the mission's explicit integration verification** — the post-merge office2 operator canary.
- **Relevant requirements**: C-002, C-004, NFR-003, SC-001…SC-004.
- **Affected surfaces**: `deploys/queued/00NN-felix-deployer-auto-rebaseline.yaml`, `CLAUDE.md` (Rebaseline obligation), the charter Rebaseline Obligation section (via charter-sync workflow, **not** a raw `.kittify` edit), `docs/runbooks/security-baseline-ops.md` (auto path + pending token + manual fallback + the **Integration verification (post-merge canary)** subsection).
- **Sequencing/depends-on**: IC-02, IC-03.
- **Integration canary (the WP05-equivalent gate)**: a pre-merge live smoke is impossible (code goes live only on the post-merge felix-deployer tick), so the integration verification is an operator-run post-deploy canary verifying SC-001 (audited-surface change → `pending_set`→`completed`, baselines healthy, zero human), SC-002 (next daily audit clean), SC-003 (non-audited change → `not_required`), SC-004 (simulated failure → exactly one ntfy + failure annotation, code left in place). Documented in `security-baseline-ops.md`; its outcome is recorded as the **merge acceptance criterion**.
- **Risks**: charter is workflow-managed — amend via charter sync, not a raw edit; this mission's own merge touches `scripts/deploy/**` (an audited surface) and predates the automation being live — so its merge is the **last manual rebaseline** (transition note in docs).

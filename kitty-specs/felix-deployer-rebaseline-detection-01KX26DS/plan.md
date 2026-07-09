# Implementation Plan: Robust Felix-Deployer Rebaseline Detection

**Branch**: `fix/felix-deployer-rebaseline-detection` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/felix-deployer-rebaseline-detection-01KX26DS/spec.md`

## Summary

Close two defects (#685) in felix-deployer's #618 auto-rebaseline so its "no operator
action" guarantee holds:

1. **Watermark-based observe range** — replace the tick's self-referential
   `pre_pull_head..post_pull_head` range with a **persisted last-observed-head
   watermark**, so `observe()` scans `last_observed_head..post_pull_head` and never
   misses an audited-surface commit that reached the checkout via an out-of-band pull.
   The watermark advances to include the deployer's own `deploy(applied)` bookkeeping
   commit so those are never re-observed.
2. **Manifest-declared expected baselines** — let a deploy manifest declare the
   baselines it will drift (e.g. `openclaw-cron.txt` for a cron removal done via CLI
   with no repo-file signal); fold those into the pending token's `expected_baselines`
   so reconcile classifies the drift as expected (D ⊆ E) and auto-rebaselines to
   `completed` instead of `unexpected_drift`.

The applier runs directly from the office2 checkout (`ExecStart=…/deployer.py`; the
tick git-pulls the same checkout), so the fix **deploys by merging to `main`** — no
`deploys/queued` manifest, and **no rebaseline** (the `scripts/deploy/**` surface has
`affected_baselines: []`).

## Technical Context

**Language/Version**: Python 3.12 (office2 runtime; code targets 3.10+, uses `from __future__ import annotations`)
**Primary Dependencies**: Standard library only for the engine (`json`, `pathlib`, `subprocess`, `datetime`, `re`, `logging`); `PyYAML` for manifest parsing (already a dependency); `pytest` for tests. **No new runtime dependencies.**
**Storage**: JSON state files on office2 at `/data/services/felix-deployer/state/` — the existing `rebaseline-pending.json` token plus a **new watermark file** `rebaseline-observed-head.json`. Baselines live at `/data/services/security-monitor/baselines/`. All paths injectable for tests.
**Testing**: `pytest` with the existing injection seams (git-runner, audit-runner, `token_path`, `registry`, `baselines_dir`); new `watermark_path` seam. Suites: `tests/deploy/test_rebaseline.py`, `tests/deploy/test_tick_rebaseline.py`, `tests/deploy/test_manifest*.py`.
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); runs as the `claude` user via the `felix-deployer.timer` systemd user unit every ~5 min.
**Project Type**: single (Python scripts + shared deploy library).
**Performance Goals**: Negligible — one extra small JSON read + one atomic write per tick (~288 ticks/day).
**Constraints**: The tick MUST never crash on rebaseline logic (returns 0); no new deps; backward compatible with existing tokens and with manifests that declare no baselines; Tier 3 change.
**Scale/Scope**: A single deployer instance; the observe range is normally 0–1 upstream commits per tick.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Assessment | Verdict |
|---|---|---|
| DIRECTIVE_001 Architectural Integrity | Watermark state + range logic live in `rebaseline.py`; tick wiring in `_tick.py`; manifest validation in `lib/manifest.py`. Each layer keeps its current responsibility; no new cross-boundary coupling. | PASS |
| DIRECTIVE_003 Decision Documentation | Watermark-advance semantics, manifest-field shape, and validation-set derivation are recorded in `research.md`. | PASS |
| DIRECTIVE_010 Specification Fidelity | C-001/C-005 amended to the verified self-pull deploy model; FRs map 1:1 to ICs below. | PASS |
| DIRECTIVE_024 Locality of Change | All code changes confined to `scripts/deploy/felix-deployer/**`, `scripts/deploy/lib/manifest.py`, `deploys/schema/manifest-v1.schema.json`, and their tests. | PASS |
| DIRECTIVE_031 Context-Aware Design | Reuses the established ubiquitous language (pending token, `expected_baselines`, `observe`/`reconcile`); the new "watermark" term is defined in the spec's Domain Language. | PASS |
| DIRECTIVE_033 / DIRECTIVE_034 | No conflict (deterministic-work routing already satisfied — this path is fully deterministic; no LLM). | PASS |
| Testing Standards / Quality Gates | New logic unit-tested via injection seams; `--cov-branch` gate honored; no live-probe modes. | PASS |
| Rebaseline Obligation (#557) | Fix touches `scripts/deploy/**` but that surface's `affected_baselines` is `[]` → **not required**; recorded on merge. | PASS |

No violations. **Complexity Tracking: N/A** (empty).

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-deployer-rebaseline-detection-01KX26DS/
├── plan.md              # This file
├── research.md          # Phase 0 — design decisions
├── data-model.md        # Phase 1 — entities: watermark, token extension, manifest field
├── quickstart.md        # Phase 1 — how to verify (tests + live confirmation on next deploy)
├── contracts/
│   └── rebaseline-range-and-baselines-v1.md   # Phase 1 — behavioral contract
└── tasks/               # (created later by /spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/deploy/
├── felix-deployer/
│   ├── rebaseline.py        # + watermark read/write; observe uses watermark base; fold_manifest_baselines()
│   └── _tick.py             # range base = watermark; collect declared baselines; advance watermark past own commits
└── lib/
    └── manifest.py          # validate optional expected_baselines field (⊆ known baselines; requires audited_surface)

deploys/schema/
└── manifest-v1.schema.json  # + optional "expected_baselines": array of baseline filenames

tests/deploy/
├── test_rebaseline.py       # + watermark read/write/fallback; fold_manifest_baselines
├── test_tick_rebaseline.py  # + out-of-band-pull repro; watermark advance; self-commit skip; declared-baseline fold
└── test_manifest*.py        # + expected_baselines validation (subset / unknown-name reject / audited_surface coupling)
```

**Structure Decision**: Single-project layout. No new modules; changes are additive
edits to three existing source files plus one JSON schema, mirrored by additive tests
in the existing `tests/deploy/` suites.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Watermark-based observe range

- **Purpose**: Make the observe range complete regardless of which actor advanced HEAD, and never re-observe the deployer's own bookkeeping commits.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004; NFR-003.
- **Affected surfaces**: `scripts/deploy/felix-deployer/rebaseline.py` (add `read_observed_head`/`write_observed_head`, atomic; keep `observe()` pure — it still takes `(base, head)`), `scripts/deploy/felix-deployer/_tick.py` (compute range base = watermark or `pre_pull_head` fallback; after observe+reconcile advance watermark to the tick's own final commit, not a blind HEAD resolve — see research.md R1).
- **Sequencing/depends-on**: none (foundational).
- **Risks**: The mid-tick out-of-band-pull race — advancing the watermark to a blind end-of-tick HEAD could skip an out-of-band commit that landed during the tick. Mitigation (R1): advance to `post_pull_head` extended only by the deployer's *own* captured commit SHA(s).

### IC-02 — Manifest-declared expected baselines

- **Purpose**: Give CLI-mutation deploys (no repo-file signal) a way to declare the baselines they drift, so reconcile treats that drift as expected.
- **Relevant requirements**: FR-005, FR-006, FR-007, FR-009; C-002, C-003.
- **Affected surfaces**: `deploys/schema/manifest-v1.schema.json` (add optional `expected_baselines`), `scripts/deploy/lib/manifest.py` (`validate_manifest`: names ⊆ known-baseline set derived from the registry union; require `audited_surface: true` when present), `scripts/deploy/felix-deployer/_tick.py` (collect declared baselines from manifests applied this tick), `scripts/deploy/felix-deployer/rebaseline.py` (`fold_manifest_baselines()` — create-or-merge the token, unioning declared baselines into `expected_baselines`).
- **Sequencing/depends-on**: IC-01 (folds into the same token observe manages).
- **Risks**: A declared-baseline deploy whose only audited-surface change is the manifest move itself must still get a token — `fold_manifest_baselines()` creates one if absent (research.md R3). Unknown baseline names must fail visibly, not silently (FR-007).

### IC-03 — No-crash, outcome stamping, backward compatibility

- **Purpose**: Preserve the tick's no-crash discipline and outcome correlation; guarantee legacy manifests/tokens are unaffected.
- **Relevant requirements**: FR-008, FR-009; NFR-001, NFR-002, NFR-005; C-003.
- **Affected surfaces**: `_tick.py` (keep rebaseline block wrapped; keep `rebaseline_stamped` correlation; watermark advance must itself be crash-safe), regression tests across all three suites.
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: Watermark write failure must degrade gracefully (log + continue), never abort the tick.

### IC-04 — Docs & merge hygiene

- **Purpose**: Restore the truthfulness of the `CLAUDE.md` "happy path" guarantee and document out-of-band robustness; record the not-required rebaseline.
- **Relevant requirements**: Architecture Impact; C-001, C-005.
- **Affected surfaces**: `CLAUDE.md` happy-path text (note robustness to out-of-band HEAD advance), the felix-deployer behavior reference doc, `docs/runbooks/security-baseline-ops.md` if it references the trigger model. Confirm the exact doc-target set against `docs/design/architecture/data/signal-to-doc-map.json` during tasks.
- **Sequencing/depends-on**: IC-01, IC-02 (docs describe shipped behavior).
- **Risks**: Missing a navigation/doc surface — mitigate via the signal-to-doc-map lookup.

## Branch Contract (repeated)

- **Current branch**: `fix/felix-deployer-rebaseline-detection`
- **Planning/base branch**: `fix/felix-deployer-rebaseline-detection`
- **Final merge target**: `fix/felix-deployer-rebaseline-detection` (this feature branch), which later lands on `main` via PR.
- `branch_matches_target`: **true**.

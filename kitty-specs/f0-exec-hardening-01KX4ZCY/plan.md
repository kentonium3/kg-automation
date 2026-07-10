# Implementation Plan: Felix Foundation-0 Exec-Hardening — Finding & Doc Reconcile

**Branch**: `feat/f0-exec-hardening` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/f0-exec-hardening-01KX4ZCY/spec.md`

## Summary

Design-phase research (see [research.md](./research.md)) established that OpenClaw's per-agent
exec **allowlist cannot hard-contain `gog`** on the worker agents without breaking their real
exec behavior (inline eval, heredocs, redirection, curl, scratch scripts). Per operator
decision, this mission **banks the unconditional wins** rather than deploying a disruptive or
leaky allowlist: it records the finding (recommending **sandbox** as the real hard-containment
lever), reconciles `service-inventory.json` + its narrative to live config (model drift +
skills fiction + stale gog-ownership), documents `main` as the tracked exception, and files a
sandbox follow-up issue. **No `openclaw.json` change** → no Tier-2 deploy, no rebaseline.

The technical approach is documentation editing gated by the architecture-data validator, plus
one GitHub issue. There is no production code and no runtime change.

## Technical Context

**Language/Version**: Markdown + JSON (docs); Python 3 only for the existing validator (`tooling/scripts/validate_architecture_data.py`). No new code.
**Primary Dependencies**: `gh` CLI (file the follow-up issue); the existing architecture-data validator; `.githooks/pre-commit` doc validation.
**Storage**: Repo files — `docs/design/felix-openclaw-boundary.md`, `docs/design/architecture/data/service-inventory.json` (authoritative JSON) + its narrative `.md` counterpart.
**Testing**: `tooling/scripts/validate_architecture_data.py` must pass on the reconciled JSON (blocking Docs-CI gate); Docs-CI markdown validation on the edited docs. No unit tests added.
**Target Platform**: Repository documentation (consumed by humans + spec/plan agents); nothing deploys to office2.
**Project Type**: single (docs/governance mission)
**Performance Goals**: N/A (documentation).
**Constraints**: No `openclaw.json`/runtime change (C-001); JSON authoritative, narrative follows (C-002); `main` out of scope (C-003); sandbox filed not built (C-004); follow-up issue is kg-automation-internal, no `@`-mentions (C-006).
**Scale/Scope**: 2 doc surfaces (boundary doc + architecture inventory JSON+narrative) + 1 GitHub issue; 6 agent inventory entries reconciled; 1 recorded finding.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_003 (Decision Documentation):** ✅ core to the mission — the finding is the decision record.
- **DIRECTIVE_010 (Specification Fidelity):** ✅ reconcile makes the docs faithful to deployed reality.
- **DIRECTIVE_024 (Locality of Change) / DIRECTIVE_033 (Targeted Staging):** ✅ small, docs-only blast radius; stage only the edited docs + mission artifacts.
- **Change-Risk Taxonomy:** ✅ effectively Tier-4 (docs/metadata) + a Tier-3 issue; no Tier-1/2 surface touched. Rebaseline obligation (#557) **not triggered** — `openclaw.json` untouched.
- **DIRECTIVE_034 (Test-First):** partially N/A — no production code; the "test" is the architecture-data validator, which must pass on the reconciled JSON. No violation to justify.

No charter violations. Complexity Tracking below is empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/f0-exec-hardening-01KX4ZCY/
├── plan.md              # This file
├── research.md          # The finding + live-config ground truth
├── data-model.md        # Reconcile-target schema (agent inventory entry)
├── quickstart.md        # How to verify the mission's outcome
└── spec.md              # Mission spec
```

### Source Code (repository root)

No source code changes. Documentation surfaces touched:

```
docs/design/felix-openclaw-boundary.md              # §8 Step 3 finding + sandbox pointer; correct stale gog-ownership (§6.1)
docs/design/architecture/data/service-inventory.json # authoritative: model drift (habits/tasker), skills reconcile, main exception, gog-only-on-main
docs/design/architecture/<narrative counterpart>.md  # narrative view follows the JSON
```

**Structure Decision:** Docs-only mission. The authoritative artifact is
`service-inventory.json` (validated by `tooling/scripts/validate_architecture_data.py`); the
boundary doc carries the narrative finding; the narrative architecture view mirrors the JSON.

## Complexity Tracking

*No charter violations — none.*

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Record the feasibility finding (boundary doc)

- **Purpose:** Capture *why* exec-allowlist hard containment was rejected and *what to do instead* (sandbox), with evidence, so the next maintainer acts without re-probing office2.
- **Relevant requirements:** FR-001, NFR-002, NFR-003.
- **Affected surfaces:** `docs/design/felix-openclaw-boundary.md` (§8 Step 3 + a finding subsection); correct the stale "calendar = sole gog owner" in §6.1 (post-#699 gog is main-only).
- **Sequencing/depends-on:** none.
- **Risks:** the finding must stay consistent with the reconciled inventory (IC-02) — same gog-ownership facts; author them together or cross-check.

### IC-02 — Reconcile the architecture inventory to live config

- **Purpose:** Make `service-inventory.json` + narrative tell the truth: habits/tasker model `haiku`; per-agent `skills` match the live Step-2 sets (calendar `[]`); `main` annotated as the tracked gog/exec exception; gog recorded as main-only.
- **Relevant requirements:** FR-002, FR-003, FR-004, NFR-001.
- **Affected surfaces:** `docs/design/architecture/data/service-inventory.json` (authoritative) + its narrative counterpart; must pass `validate_architecture_data.py`.
- **Sequencing/depends-on:** none (can proceed in parallel with IC-01; share the gog-ownership facts).
- **Risks:** validator schema constraints (STATUS_ENUM / field shapes) — run the validator locally before commit; the `updated_by` provenance string convention must be preserved.

### IC-03 — File the sandbox hard-containment follow-up + link it

- **Purpose:** Route the deferred hard-containment work to a tracked issue so Foundation-0's remaining hard boundary isn't lost.
- **Relevant requirements:** FR-005, C-006.
- **Affected surfaces:** a new kentonium3/kg-automation issue (infra template); a back-link added in boundary-doc §8 Step 3.
- **Sequencing/depends-on:** the finding (IC-01) should exist first so the issue can cite it.
- **Risks:** kg-automation-internal issue (repo-scoped copy-approval exception applies) — but still no `@`-mentions of outsiders; use the infra issue template + symptom/observer/cost framing.

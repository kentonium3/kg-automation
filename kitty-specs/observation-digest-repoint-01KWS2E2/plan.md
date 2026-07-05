# Implementation Plan: Observation-Digest Log Repoint & Decommission

**Branch**: `fix/observation-digest-repoint` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/observation-digest-repoint-01KWS2E2/spec.md`
**Source issue**: kentonium3/kg-automation#659 (fast-follow to #656)

## Summary

Repoint the observation-digest subsystem's raw `log_dir` default off the stray
`/home/claude/second-brain/agents/logs` tree onto the backed-up vault-account path
`/home/kgale/second-brain/agents/logs`, migrate the historical raw logs there, then fully
decommission `/home/claude/second-brain`. The digest **output** path is already vault-synced
and is unchanged; the arch docs that record it on the stray tree are stale and are corrected.
Delivery is a Python code change (config default + docstrings), a one-time migration/decommission
deploy helper (reusing the #656 machinery), a `deploys/queued` manifest applied by felix-deployer
under a Tier-2 Restic snapshot gate, and architecture-doc corrections.

## Technical Context

**Language/Version**: Python 3.12 (office2 system `python3`; repo modules target 3.10+)
**Primary Dependencies**: Python standard library only (`pathlib`, `json`, `shutil`, `argparse`); reuses in-repo `scripts/deploy/lib/` (snapshot/apply/verify/tier), `scripts/deploy/migrate-inbox-state-and-logs.py` machinery, and `scripts/vault/resolver.py`; Restic (external) for the snapshot gate; felix-deployer for application
**Storage**: Filesystem — per-agent JSONL logs (`agents/logs/{agent}/YYYY-MM-DD.jsonl`); no database
**Testing**: pytest (`scripts/openclaw/observation/tests/`, deploy-helper tests) + a subprocess/shebang regression test for the migrator entrypoint (dry-run exits 0, `+x` bit, `sys.path` shim)
**Target Platform**: office2 (Ubuntu 24.04 LTS); systemd **user** services under user `claude`
**Project Type**: single (Python scripts within the kg-automation repo)
**Performance Goals**: N/A — one-time batch migration over a small file set; digest cadence (15 min) unaffected
**Constraints**: Tier-2 Restic snapshot gate before any destructive step; idempotent + convergent; no digest downtime; all office2 changes via the `deploys/queued` manifest pipeline; #557 rebaseline obligation (deploy-pipeline audited surface)
**Scale/Scope**: Small — a handful of per-agent log subdirectories on a single host

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter loaded in compact mode. Relevant gates and their disposition:

- **Change-Risk Taxonomy (Tier Protocol)** — PASS. Tier 2 (data/log migration; snapshot-gated) + Tier 3 (Python config) + Tier 4 (arch-doc JSON). No Tier 0/1 (no host/system-unit, network, or firewall change; user-unit files are untouched). Snapshot gate satisfies Tier-2 protocol.
- **Rebaseline Obligation (#557)** — PASS by design. The `deploys/queued/*.yaml` manifest matches the `deploy-pipeline` audited surface; felix-deployer's happy-path auto-rebaseline handles it; the merge commit records the outcome. No systemd-unit edit → `systemd-user-units` surface not triggered.
- **Deployment Constraints (manifest discipline)** — PASS. Delivery is a `deploys/queued/NNNN-*.yaml` manifest; no out-of-band office2 changes.
- **DIRECTIVE_024 Locality of Change** — PASS. One config-default line + one migrator helper + one manifest + doc corrections; blast radius bounded to the observation subsystem.
- **DIRECTIVE_003 Decision Documentation** — the one design decision (log-dir default mechanism) is recorded in `research.md` with rationale and rejected alternative.
- **DIRECTIVE_010 Specification Fidelity** — plan traces every FR/NFR/C to an implementation concern below.

No unjustified gate violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/observation-digest-repoint-01KWS2E2/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (migrator CLI contract)
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/
├── openclaw/observation/
│   ├── config.py                       # FR-001: repoint log_dir default; FR-007: docstring
│   ├── log_action.py                   # FR-007: docstring only (writes via config.log_dir)
│   └── summarize.py                    # FR-007: docstring only (reads via config.log_dir)
├── vault/
│   └── (resolver.py / paths.json)      # touched ONLY if registry mechanism chosen (see research.md)
└── deploy/
    ├── observation_migration.py            # NEW: importable logic module (union-merge, gates, quiesce, delete)
    ├── migrate-observation-logs.py         # NEW Phase-1 wrapper: FR-002/005 migrate-only (non-destructive)
    ├── decommission-observation-stray-tree.py  # NEW Phase-2 wrapper: FR-003/004 quiesce + gate + root-only rm
    ├── migrate-inbox-state-and-logs.py     # REUSED machinery reference (union-merge, snapshot gate)
    └── lib/                                # REUSED shared deploy library

deploys/queued/
├── NNNN-migrate-observation-logs.yaml              # FR-008/FR-009 Phase 1 (Tier-2, non-destructive)
└── MMMM-decommission-observation-stray-tree.yaml   # FR-009 Phase 2 (queued after Phase 1 verified)

docs/design/architecture/data/
├── service-inventory.json              # FR-006: felix-core-digest corrections
└── data-flows.json                     # FR-006: observation-digest flow corrections
  (+ regenerated markdown views)

tests/ (co-located under scripts/**/tests or scripts/openclaw/observation/tests)
└── migrator + config-default + shebang regression tests   # NFR-003/NFR-004
```

**Structure Decision**: Single-project Python layout matching the existing kg-automation
`scripts/<domain>/` convention. The new migrator is a **domain-co-located deploy helper**
under `scripts/deploy/` (sibling of the #656 migrator), per helper-script-conventions §9 and
spec FR-008.

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Repoint the log-dir default (code)

- **Purpose**: Make the observation `log_dir` default resolve to the backed-up vault path independent of `HOME`, so cron-run agents stop writing to the stray tree.
- **Relevant requirements**: FR-001, FR-007; C-002 (do not touch output dir), C-005 (not under `notes/`).
- **Affected surfaces**: `scripts/openclaw/observation/config.py` (line 40 default + docstring); docstrings in `log_action.py`, `summarize.py`. Possibly `scripts/vault/paths.json` + `resolver.py` (mechanism decided in research.md).
- **Sequencing/depends-on**: none.
- **Risks**: script-path invocation (`/usr/bin/python3 …/summarize.py`, not `-m`) means the import surface must keep working; the existing `sys.path` shim in `config.py` covers `scripts.vault.resolver`. A config-default unit test locks FR-001.

### IC-02a — Phase 1: migrate observation logs (non-destructive) + logic module

- **Purpose**: Union-merge runtime observation logs (`agents/logs/{agent}/*.jsonl`) from the stray tree into the vault, atomically (temp+`os.replace`), idempotently. **No deletion.** House the shared logic in an importable underscore module.
- **Relevant requirements**: FR-002, FR-005, FR-009 (Phase 1); NFR-003 (no loss), NFR-004 (shebang/dry-run), NFR-005 (atomic merge), C-011 (vault writability).
- **Affected surfaces**: NEW `scripts/deploy/observation_migration.py` (importable module) + `scripts/deploy/migrate-observation-logs.py` (thin executable wrapper); reuse union-merge/snapshot-gate helpers; co-located tests.
- **Sequencing/depends-on**: IC-01 (repoint is Phase 1's code).
- **Risks**: a concurrent cron append during migrate is harmless (non-destructive; stragglers caught next cycle + Phase-2 final merge). Merge MUST be atomic (Codex Major 3). Entrypoint import name must be underscore-importable (Codex Major 4).

### IC-02b — Phase 2: decommission the stray tree (destructive, gated)

- **Purpose**: After Phase 1 is verified, quiesce the timer, run the precondition gate, final-merge stragglers, then root-only `rm -rf` the `/home/claude/second-brain` clone — never touching `_private`.
- **Relevant requirements**: FR-003, FR-004, FR-009 (Phase 2); NFR-001 (snapshot+coverage); C-008 (`_private`/no-walk), C-009 (recoverability), C-010 (authorized `DM-01KWS4F986PVHTJRSHZPQACDM7`).
- **Affected surfaces**: NEW `scripts/deploy/decommission-observation-stray-tree.py` (wrapper over the module); co-located tests.
- **Sequencing/depends-on**: IC-02a AND a verified clean digest cycle (Phase 1 confirmed) — enforced by staging the Phase-2 manifest separately.
- **Reality note**: the stray tree is a git clone of `kentonium3/second-brain` (March vault snapshot + old digest/state + live logs + `_private`), NOT a bare log dir. Only runtime logs are migrated; tracked content is recoverable from origin; everything else is removed in place without inspection.
- **Risks (Codex Critical 1+2)**: `rm -rf` of a second-brain clone — gate on ALL of: fresh snapshot **+ proof the source root is in the backup set** (recency insufficient) OR operator attestation; HEAD present on origin; timer quiesced + no live `summarize.py`/`log_action.py`; inbox-prescan mtime check. Abort-before-delete on any failure. Root-only deletion; NO `rglob`/`os.walk`/`git status --ignored`; errors name only `source_root`.

### IC-03 — Deploy manifests (two, staged)

- **Purpose**: Express Phase 1 (migrate, non-destructive) and Phase 2 (decommission) as **two separate** felix-deployer manifests, each Tier-2 snapshot-gated, so Phase 2 is queued only after Phase 1 is verified over ≥1 clean cycle.
- **Relevant requirements**: FR-008, FR-009; C-006 (manifest pipeline), C-007 (rebaseline), NFR-001, NFR-002 (no downtime).
- **Affected surfaces**: NEW `deploys/queued/NNNN-migrate-observation-logs.yaml` (Phase 1) and `deploys/queued/MMMM-decommission-observation-stray-tree.yaml` (Phase 2).
- **Sequencing/depends-on**: Phase-1 manifest → IC-02a; Phase-2 manifest → IC-02b + verified Phase 1. `apply.py` invokes `[entrypoint, "--apply"]` only, so staged behavior lives in two entrypoints, not flags (Codex Major 1).
- **Risks**: each entrypoint must survive felix-deployer's shebang invocation (NFR-004); both manifests are the audited surface that triggers rebaseline. Phase-2 manifest MUST NOT be applied before Phase-1 verification — operator stages it deliberately.

### IC-04 — Architecture-doc corrections

- **Purpose**: Bring `service-inventory.json` and `data-flows.json` (+ markdown views) into agreement with reality: vault log path, corrected stale `output_path`, corrected `exec_start` `repos/` discrepancy, removed `#659` `path_retention_note`s.
- **Relevant requirements**: FR-006; SC-005.
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json` (felix-core-digest), `docs/design/architecture/data/data-flows.json` (observation-digest), regenerated markdown views.
- **Sequencing/depends-on**: none (can proceed in parallel with IC-01/02); must reflect the final chosen paths.
- **Risks**: the architecture-data validator is a blocking Docs-CI gate — JSON must stay schema-valid with `updated_by: 659`.

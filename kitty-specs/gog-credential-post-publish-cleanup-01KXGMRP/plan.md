# Implementation Plan: gog credential post-publish cleanup

**Branch**: `feat/731-gog-cred-post-publish-cleanup` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/gog-credential-post-publish-cleanup-01KXGMRP/spec.md`

## Summary

Remove the obsolete "7-day Testing-app" assumptions from Felix's credential-liveness
probe now that the Google OAuth app is published. Collapse the probe's
routine/unexpected classification into a single `dead` state, delete the dead `#616`
cycle-baseline machinery, and correct `gog-reauth.sh`'s stale wording and consent-
screen guidance. Code + docs only; no live-token action.

## Technical Context

**Language/Version**: Python 3.12 (office2 `/usr/bin/python3`) + Bash (POSIX, `gog-reauth.sh`)
**Primary Dependencies**: standard library only (`subprocess`, `dataclasses`, `datetime`, `json`, `glob`); pytest for tests
**Storage**: `docs/design/architecture/data/credential-manifest.json` (in-repo JSON config)
**Testing**: pytest with `--cov-branch`; `tests/security/test_liveness.py`, `tests/security/test_orchestrator.py`
**Target Platform**: office2 (Ubuntu 24.04), `credential-liveness-probe.service` systemd user timer (6h)
**Project Type**: single (Python package under `scripts/security/credential_health_check/`)
**Performance Goals**: unchanged — 15s probe timeout, 6h cadence
**Constraints**: `reauth_marker_glob` removal must be atomic across `manifest.py` + `credential-manifest.json` (unknown-key rejection); maintain branch coverage; touch only credential-liveness/gog-reauth occurrences (not unrelated `7-day` strings)
**Scale/Scope**: 4 code files, 2 test files, ~6 doc/data files; one gog credential currently probed

**Runtime detail**: `ExecStart=/usr/bin/python3 -m scripts.security.credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json --liveness-only`, `WorkingDirectory=/home/claude/kg-automation`, `PYTHONPATH=/home/claude/kg-automation`.
**Deploy**: felix-deployer `git pull origin/main` into the office2 checkout; routine picks up new code on next 6h tick. **No `deploys/queued` manifest** (no systemd/service/cron/out-of-checkout change).
**Rebaseline**: **Not required** — no touched path matches an audited surface in `audited-surfaces.json` (only `scripts/security/ssh-keys/*` is audited under `scripts/security/`).
**Change-risk tier**: Tier 3 (logic/workflow).

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — still passing.*

Charter present (`compact` mode). Relevant directives:
- **DIRECTIVE_001 (Architectural Integrity)**: `liveness.py` owns classification, `orchestrator.py` owns alerting; the collapse simplifies both without new coupling. ✅
- **DIRECTIVE_003 (Decision Documentation)**: collapse-vs-gate decision recorded in spec §Scope Decision + research.md. ✅
- **DIRECTIVE_010 (Specification Fidelity)**: spec C-001 corrected once research disproved the audited-surface assumption. ✅
- **Testing Standards / Quality Gates**: full pytest + `--cov-branch` maintained (NFR-002). ✅
- **Rebaseline Obligation**: verified N/A. ✅

No charter conflicts. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this mission)

```
kitty-specs/gog-credential-post-publish-cleanup-01KXGMRP/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── liveness-classification.md   # Phase 1
└── tasks/               # /spec-kitty.tasks output (later)
```

### Source Code (repository root)

```
scripts/security/
├── credential_health_check/
│   ├── liveness.py       # IC-01: collapse classification, delete baseline machinery
│   ├── manifest.py       # IC-02: drop reauth_marker_glob from schema
│   └── orchestrator.py   # IC-03: single-classification alert construction
└── gog-reauth.sh         # IC-04: wording + consent guidance

docs/design/architecture/
├── data/
│   ├── credential-manifest.json   # IC-02 (config key) + IC-06 (narrative fields)
│   └── service-inventory.json     # IC-06
└── service-inventory.md           # IC-06
docs/INDEX.md                      # IC-06
docs/runbooks/credential-liveness-probe-ops.md   # IC-06
docs/runbooks/google-workspace-ops.md            # IC-06

tests/security/
├── test_liveness.py       # IC-05
└── test_orchestrator.py   # IC-05
```

**Structure Decision**: Single Python package; no new modules. All changes are in-place edits to existing files above.

## Key Design Decisions (detail in research.md)

1. **Single classification value = `dead`.** `LivenessClassification = Literal["dead", "probe-error"]`. Title prefix → `credential-liveness-dead: <name>`.
2. **Delete baseline machinery**: `_resolve_cycle_baseline()`, `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`, all `reauth_marker_glob` handling. The dead path no longer reads `keyring_file` mtime.
3. **Atomic `reauth_marker_glob` removal** across `manifest.py` (`allowed_keys` + dataclass) and `credential-manifest.json` — unknown `liveness_probe` keys raise `ManifestQualityError`, so both edits land together.
4. **`keyring_file` stays** — descriptive, not part of the removed machinery; still required when `enabled`.
5. **`orchestrator._build_liveness_issue_body`**: the `dead-unexpected` "investigate at myaccount.google.com/permissions" block becomes **unconditional**.
6. **`orchestrator` title**: `removeprefix('dead-')` on `dead` → `dead` → `credential-liveness-dead: <name>`.
7. **Documented behavioral shift**: `invalid_grant` + absent keyring now → `dead` (was `probe-error`), since keyring is no longer stat-ed. Strictly better; test updated.

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Collapse probe classification + delete baseline machinery
- **Purpose**: Make the probe classify every dead OAuth credential as a single genuinely-unexpected `dead`, removing the now-false 7-day routine concept.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-005, NFR-001, NFR-003, NFR-004
- **Affected surfaces**: `scripts/security/credential_health_check/liveness.py`
- **Sequencing/depends-on**: none
- **Risks**: preserve the alive→`None` and probe-error paths exactly; ensure the `invalid_grant` branch no longer references baseline/keyring.

### IC-02 — Remove `reauth_marker_glob` from schema (atomic with config)
- **Purpose**: Delete the dead config field so the schema matches reality.
- **Relevant requirements**: FR-003, NFR-004
- **Affected surfaces**: `scripts/security/credential_health_check/manifest.py`, `docs/design/architecture/data/credential-manifest.json`
- **Sequencing/depends-on**: coupled with IC-01 (same conceptual change); the two edits here are atomic with each other.
- **Risks**: unknown-key rejection means the JSON key must be removed in the same commit as the `allowed_keys` change.

### IC-03 — Single-classification alert construction
- **Purpose**: Update the alert writer to the collapsed classification (unconditional investigate block, `credential-liveness-dead` title).
- **Relevant requirements**: FR-004
- **Affected surfaces**: `scripts/security/credential_health_check/orchestrator.py`
- **Sequencing/depends-on**: follows IC-01 (uses the new classification value)
- **Risks**: keep dedup working; note that pre-existing open liveness issues with old titles (e.g. #629 `-unexpected`) won't dedup against the new `-dead` title — recommend closing stale ones (operator note, not code).

### IC-04 — Correct `gog-reauth.sh` wording + consent guidance
- **Purpose**: Remove the false 7-day/Testing claims and describe the real consent screen (10 boxes; org-directory decline-by-default).
- **Relevant requirements**: FR-006, FR-007
- **Affected surfaces**: `scripts/security/gog-reauth.sh`
- **Sequencing/depends-on**: none (independent of the Python change)
- **Risks**: the script self-updates via `git pull` at run time — keep that mechanism; only change comments/echo text, not the auth flow.

### IC-05 — Rewrite tests for single-classification behavior
- **Purpose**: Validate the collapsed behavior and the absence of removed machinery; maintain coverage.
- **Relevant requirements**: FR-009, NFR-002
- **Affected surfaces**: `tests/security/test_liveness.py`, `tests/security/test_orchestrator.py`
- **Sequencing/depends-on**: validates IC-01/IC-02/IC-03
- **Risks**: delete the 5 reauth-marker tests + keyring-fallback-source test; collapse timing/routine/unexpected tests to one `invalid_grant → dead`; update keyring-missing test to expect `dead`; keep alive/probe-error/UTC/disabled cases; hold `--cov-branch` (add `# pragma: no branch` only where a defensive branch is provably unreachable).

### IC-06 — Update architecture data + narrative + runbooks
- **Purpose**: Keep docs faithful — drop routine-7day / Testing-app framing; describe the single `dead` classification.
- **Relevant requirements**: FR-008, SC-006
- **Affected surfaces**: `docs/design/architecture/data/credential-manifest.json` & `service-inventory.json`, `docs/design/architecture/service-inventory.md`, `docs/INDEX.md`, `docs/runbooks/credential-liveness-probe-ops.md`, `docs/runbooks/google-workspace-ops.md`
- **Sequencing/depends-on**: none (docs); credential-manifest.json config key also covered by IC-02
- **Risks**: touch only credential-liveness/gog occurrences; leave unrelated `7-day` strings alone (C-005).

## Branch contract (restated)

- Current branch at plan: `feat/731-gog-cred-post-publish-cleanup`
- Planning/base branch: `feat/731-gog-cred-post-publish-cleanup`
- Mission merge target: `feat/731-gog-cred-post-publish-cleanup`
- After post-merge Codex review of the full mission diff → `feat/731 → main` (manual) → felix-deployer git-pull deploy on office2.

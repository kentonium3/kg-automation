# Implementation Plan: Felix-deployer ntfy Failure Notifications

**Branch**: `kitty/mission-felix-deployer-ntfy-failure-notifications-01KTZ76F` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/spec.md`

**Final merge target**: `main` (after `/spec-kitty.merge`)

## Summary

Replace `scripts/deploy/felix-deployer/notify.py`'s broken openclaw-cron WhatsApp DM dispatch with a direct ntfy.sh push via `curl`. Strip step 5 (the openclaw cron registration) from `scripts/deploy/deploy-felix-deployer-bootstrap.sh`. Mint a new `ntfy-notification-v1.md` contract documenting title+body rendering. Update architecture data (data-flows, service-inventory, credential-manifest) to reflect the new outbound HTTP flow and the new `FELIX_DEPLOYER_NTFY_TOPIC` env credential. The applier on office2 stays live and ticking; once merged, the operator re-runs `--rollback` then `--apply` to swap the broken applier for the fixed one. Code-only acceptance per spec C-004.

## Technical Context

**Language/Version**: Python 3.11+ (existing — `scripts/deploy/felix-deployer/*.py`), Bash 5.x (existing — `scripts/deploy/deploy-felix-deployer-bootstrap.sh`).
**Primary Dependencies**: `pytest` 8.x with `subprocess` monkeypatching (no new HTTP client dep). `curl` (system, invoked via `subprocess.run`). `scripts.deploy.lib.LibResult` (existing internal). `scripts.deploy.lib.verify.redact_secrets` (existing internal).
**Storage**: N/A — notifications are ephemeral HTTP POSTs. Persistent failure state is the existing `deploys/failed/<manifest>/` artifact (unchanged).
**Testing**: pytest in `tests/deploy/`. Subprocess `curl` calls mocked via `monkeypatch.setattr(subprocess, "run", ...)` or `subprocess.run` wrapper injection — same pattern used by `tests/deploy/test_deployer.py` for `openclaw` mocks. No live ntfy integration test in CI (per spec out-of-scope).
**Target Platform**: office2 (Ubuntu 24.04 LTS) for the applier; Mac for development and the bootstrap script's local-side. Repo CI runs on Linux GitHub-hosted runners (`ubuntu-latest`).
**Project Type**: single (existing repo layout under `scripts/deploy/`).
**Performance Goals**: Notification dispatch ≤ 10 seconds end-to-end (curl `--max-time 10`). Applier tick total time ≤ existing tick budget + 10 s headroom. Test suite for notify-touched files ≤ 5 s wall-clock.
**Constraints**:
- No new Python HTTP dependency (curl-via-subprocess per spec C-005).
- No openclaw cron registration anywhere in the dispatch path (per spec C-002).
- Notify failure NEVER crashes the applier tick (per spec C-003).
- Topic env value never committed (per spec C-006).
**Scale/Scope**: Single recipient (operator). ≤5 notifications per day expected (deploy failures are rare). One topic, one subscriber.

## Charter Check

Loaded `.kittify/doctrine` charter context (action=plan): software-dev-default, directives DIRECTIVE_001/003/010/024/031/033/034. No `.kittify/charter/charter.md` is referenced from current context; the project charter lives at `docs/constitution/FELIX-CONSTITUTION.md` (project-specific) and is the source of truth.

| Directive | Outcome | Notes |
|---|---|---|
| DIRECTIVE_001 (Architectural Integrity) | ✅ Pass | notify.py remains a single-responsibility module with one public function; failure isolation invariant preserved (tick-never-crashes). |
| DIRECTIVE_003 (Decision Documentation) | ✅ Pass | Substrate choice (ntfy > openclaw cron) is documented in spec Assumptions + this plan's research.md. The 0001-vs-0002 applied-entry decision is documented in research.md. |
| DIRECTIVE_010 (Specification Fidelity) | ✅ Pass | Every FR in spec.md maps to an IC below (FR→IC traceability in IC notes). |
| DIRECTIVE_024 (Operational Symptom) | ✅ Pass | Source issue #595 names the symptom (operator gets no DM on failure), observer (operator during bootstrap apply), and cost (operator must manually poll failed/, defeating FR-009 of the parent mission). |
| DIRECTIVE_031 (Tier-Aware Change Control) | ✅ Pass | Tier 3 logic change; no Tier 2 secret-bearing env file (the topic value is non-secret but private; the topic file mode is the only guard). Pre-flight checklist not required for Tier 3. |
| DIRECTIVE_033 (Helper-Script Conventions) | ✅ Pass | notify.py is a library invoked by `_tick.py`; tested independently; no agent prompt change. Three-tier model: notify.py is a library (tier 2) — pure functions + a small subprocess wrapper, no CLI surface. |
| DIRECTIVE_034 (Self-Documenting Surfaces) | ✅ Pass | env.sample documents the topic-setup procedure; ntfy-notification-v1.md documents the wire shape; signal-to-doc-map already covers the touched arch surfaces. |

Project Charter additional gates (per `docs/constitution/FELIX-CONSTITUTION.md`):

- **Rebaseline Obligation (#557)**: applies (this mission touches `scripts/deploy/deploy-felix-deployer-bootstrap.sh` and `scripts/deploy/felix-deployer/*`, both in `docs/design/architecture/data/audited-surfaces.json`). Covered by spec FR-015 and tracked in WP for merge-commit rebaseline annotation.
- **Change-Risk Taxonomy (Tier Protocol)**: Tier 3. No Tier 0 surfaces touched. No Tier 2 service env-file modification on a hot-path secret (the new `EnvironmentFile=` carries a non-secret topic). Tier 3 protocol allows direct apply with dry-run/sandbox verification — covered by `--dry-run` mode in the bootstrap script + pytest mock coverage.
- **Deployment Constraints**: The deploy-discipline mission ships in main as of `48c60c32`. This mission uses the discipline's terminology (manifest, applier, failure record) and updates the bootstrap-wrapper precedent without compromising the pull-only model.

No charter violations. No `Complexity Tracking` entries needed.

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/
├── plan.md                      # This file (this command's output)
├── research.md                  # Phase 0: substrate justification + 0001-vs-0002 decision
├── data-model.md                # Phase 1: notification entity + env file shape
├── quickstart.md                # Phase 1: end-to-end operator walkthrough post-merge
├── contracts/
│   └── ntfy-notification-v1.md  # Phase 1: title+body wire-shape contract
├── spec.md                      # (already committed)
├── checklists/requirements.md   # (already committed)
└── meta.json                    # (already present)
```

### Source Code (repository root)

```
scripts/deploy/felix-deployer/
├── notify.py                    # REWRITTEN: ntfy.sh substrate (was openclaw cron)
├── _tick.py                     # UPDATED: dispatch call renamed; PHASE map renamed
├── env.sample                   # NEW: FELIX_DEPLOYER_NTFY_TOPIC= template
├── felix-deployer.service       # UPDATED: gains EnvironmentFile=
├── felix-deployer.timer         # (unchanged)
└── deployer.py / _entrypoint.py # (unchanged callers)

scripts/deploy/
└── deploy-felix-deployer-bootstrap.sh   # UPDATED: step 5 removed; --apply syncs env.sample target

tests/deploy/
├── test_deployer.py             # UPDATED: dispatch failure path expectations
├── test_notify.py               # NEW: payload rendering, redaction, error classes
└── (other test_*.py unchanged)

docs/design/architecture/
├── data/
│   ├── data-flows.json          # UPDATED: new outbound entry (felix-deployer → ntfy.sh)
│   ├── service-inventory.json   # UPDATED: felix-deployer env-file dep + outbound URL
│   ├── credential-manifest.json # UPDATED: FELIX_DEPLOYER_NTFY_TOPIC entry
│   └── (audited-surfaces.json unchanged — already includes touched paths)
├── data-flows.md                # UPDATED: narrative for new flow
├── data-flows.view.md           # UPDATED: Mermaid diagram if applicable
├── service-inventory.md         # UPDATED: felix-deployer service row
├── credentials-and-secrets.md   # UPDATED: env credential entry
└── identity-model.md            # UPDATED if env credential touches identity surface

docs/design/
└── felix-capability-roadmap.md  # UPDATED: felix-deployer capability row (substrate swap)
```

**Structure Decision**: Single-project layout. No new directories at the repo root; all changes land inside the existing `scripts/deploy/`, `tests/deploy/`, and `docs/design/architecture/` trees. The kitty-specs mission directory holds the planning artifacts plus the new contract.

## Implementation Concern Map

The work splits into seven concerns. They will collapse into 2–3 WPs in `/spec-kitty.tasks` — one large code-rewrite WP, one docs/contract WP, possibly a tests-only WP if needed for review granularity.

### IC-01 — notify.py rewrite (substrate swap)

- **Purpose**: Replace the broken openclaw-cron dispatch with a direct ntfy.sh POST via curl; preserve the redact-then-truncate invariant and the failure isolation semantics.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-009, FR-013, FR-014.
- **Affected surfaces**: `scripts/deploy/felix-deployer/notify.py` (full rewrite). New unit tests in `tests/deploy/test_notify.py`.
- **Sequencing/depends-on**: none (entry concern).
- **Risks**: subprocess return-code semantics for curl vary by failure mode (DNS, connect, HTTP 5xx). Mitigation: classify by curl exit code + HTTP status header parse; emit a stable `error_code` per LibResult.

### IC-02 — `_tick.py` integration update

- **Purpose**: Update the only caller of the retired `dispatch_failure_dm` to use the new `dispatch_failure_notification`. Rename `PHASE_TO_DM_PHASE` → `PHASE_TO_NOTIFY_PHASE`. No semantic change to phase collapse.
- **Relevant requirements**: FR-010.
- **Affected surfaces**: `scripts/deploy/felix-deployer/_tick.py`. Updates to `tests/deploy/test_deployer.py` for the renamed symbols and updated mock targets.
- **Sequencing/depends-on**: IC-01 (must follow notify.py rewrite for symbol existence).
- **Risks**: existing tests pin behavior; symbol renames break collection. Mitigation: rename in same commit as the call-site update; run full deploy test suite locally before commit.

### IC-03 — Bootstrap script step-5 removal + env-file plumbing

- **Purpose**: Remove the broken openclaw cron registration from `--apply` mode and from the `--dry-run` preview text. Add deployment of an env file populated from a non-committed template on office2. Update header comments to reflect the substrate change.
- **Relevant requirements**: FR-005, FR-006, FR-007, SC-007.
- **Affected surfaces**: `scripts/deploy/deploy-felix-deployer-bootstrap.sh` (remove step 5; renumber step 6 → step 5; renumber step 7 → step 6; or keep 7-step numbering with a clearly-marked "step 5 (retired)" slot — to be settled at code-write time, leaning toward renumber-to-6 for cleanliness). `scripts/deploy/felix-deployer/felix-deployer.service` (add `EnvironmentFile=-/home/claude/.config/felix-deployer/env`; the `-` prefix makes a missing file non-fatal at unit start). New `scripts/deploy/felix-deployer/env.sample` template.
- **Sequencing/depends-on**: parallelisable with IC-01.
- **Risks**: env file path mismatch between the systemd unit and the bootstrap script's mkdir target → applier silently runs with empty `FELIX_DEPLOYER_NTFY_TOPIC`. Mitigation: single canonical constant in bootstrap script header; reference it in both places; smoke-test path resolution in `--dry-run`.

### IC-04 — ntfy-notification-v1 contract artifact

- **Purpose**: Author the wire-shape contract describing title+body rendering, redact-then-truncate invariant, header conventions (Title/Priority/Tags), and error-code taxonomy.
- **Relevant requirements**: FR-008, SC-004.
- **Affected surfaces**: `kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md`.
- **Sequencing/depends-on**: IC-01 (write the contract from the actual rendering code's output for fidelity; or write the contract first and follow it — call at code-time, but contract MUST land in the same WP as notify.py rewrite so review can cross-check).
- **Risks**: contract written before code drifts from code. Mitigation: bundle in same WP; reviewer rejects on drift.

### IC-05 — Architecture data updates

- **Purpose**: Update `data-flows.json` + `service-inventory.json` + `credential-manifest.json` plus the narrative markdown counterparts to reflect the new outbound HTTP flow and the new env credential.
- **Relevant requirements**: FR-011, SC-006.
- **Affected surfaces**: `docs/design/architecture/data/data-flows.json`, `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/data/credential-manifest.json`, `docs/design/architecture/data-flows.md`, `docs/design/architecture/data-flows.view.md`, `docs/design/architecture/service-inventory.md`, `docs/design/architecture/credentials-and-secrets.md`, optionally `docs/design/architecture/identity-model.md` and `docs/design/felix-capability-roadmap.md`.
- **Sequencing/depends-on**: parallelisable with IC-01/IC-03 once the wire shape is settled.
- **Risks**: schema validation failures on JSON edits. Mitigation: validate locally against schema before commit (the JSONs have JSON Schema partners in the same dir).

### IC-06 — Test coverage

- **Purpose**: Cover payload rendering, redaction, truncation, dispatch-success, and each dispatch-failure mode (NTFY_UNREACHABLE, NTFY_HTTP_ERROR, NTFY_MISSING_TOPIC, NTFY_CURL_MISSING) with deterministic mocks.
- **Relevant requirements**: FR-013, SC-001, SC-002, SC-003.
- **Affected surfaces**: `tests/deploy/test_notify.py` (new), `tests/deploy/test_deployer.py` (updated mock targets).
- **Sequencing/depends-on**: IC-01 (test code references notify.py API).
- **Risks**: test brittleness on curl exit-code semantics. Mitigation: use `subprocess.CompletedProcess`-shaped mocks; assert on `LibResult.details["error_code"]` not on stderr substring matching.

### IC-07 — Rebaseline obligation annotation

- **Purpose**: Ensure the merge commit carries `Rebaseline: completed at <ts>` per #557.
- **Relevant requirements**: FR-015.
- **Affected surfaces**: merge-commit message (recorded at `/spec-kitty.merge` time, not authored as a file).
- **Sequencing/depends-on**: must precede merge.
- **Risks**: forgotten at merge time → audited-surface-reminder CI annotates the push with a soft reminder. Mitigation: surface it explicitly in `quickstart.md`'s post-merge checklist.

## Complexity Tracking

No charter violations. Section deliberately empty.

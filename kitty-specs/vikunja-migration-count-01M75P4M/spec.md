# Mission Specification: Vikunja release route takes the migration count from the release, not a constant

**Mission Branch**: `fix/vikunja-migration-count` (from `main` `67ac02c0`)
**Created**: 2026-11-11 · **Status**: Draft · **Input**: kentonium3/kg-automation#1098. Lead 24d09460, bus request 20261110T215747798808Z9dc49d3364. Kent authorized the push and PR directly on 2026-11-11; the merge and every Office2 step stay Kent's.

## Intent Summary (decision `01M75P5HRGS39PMDQKA0BPWNZJ`)

- **Problem.** The Vikunja release route assumes a release adds exactly 10 migrations, which was true of `v2.8.0-rrule.2`. `v2.8.0-rrule.3` adds 0, so the route cannot build its baseline, and acceptance would fail a correct upgrade.
- **Outcome.** The expected migration set comes from the release's reviewed inputs. Releases adding 10 or 0 both build, gate and verify, and any mismatch still fails closed. The change-set tests accept a STAGE whose predecessor is `v2.8.0-rrule.2`.
- **Out of scope.** The rrule.3 release record, baseline and manifests themselves, and any Office2 step. Those are the later STAGE and ACTIVATE PRs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stage a release with a different migration count (Priority: P1)

The operator builds the qualified baseline for a release that adds 0 migrations (or 10, or any reviewed number) and the route accepts it.

**Independent Test**: build baselines from fixture pre/post copies that differ by 10 and by 0 migrations, with the matching expected count; both succeed. A wrong expected count fails.

**Acceptance Scenarios**:

1. **Given** pre and post copies differing by 10 migrations and an expected count of 10, **When** the baseline is built, **Then** it succeeds with those 10 IDs.
2. **Given** identical migration sets and an expected count of 0, **When** the baseline is built, **Then** it succeeds with `added_migration_ids: []`.
3. **Given** any mismatch between the expected count and the observed difference, or a migration lost from pre to post, **When** the baseline is built, **Then** it fails with `GATE_MIGRATIONS_MISMATCH` and writes nothing.

### User Story 2 - Accept an upgrade that adds no migrations (Priority: P1)

**Independent Test**: run the acceptance verifier on a snapshot and post copy whose committed baseline has `added_migration_ids: []`.

**Acceptance Scenarios**:

1. **Given** a baseline with 0 added IDs bound by its sha in the release record, **When** acceptance runs on a correct upgrade, **Then** every check passes.
2. **Given** the same, with a post copy that gained or lost a migration, **When** acceptance runs, **Then** `MIGRATIONS` fails.
3. **Given** the existing 10-ID baseline, **When** acceptance runs, **Then** behaviour is unchanged.

### User Story 3 - Change-set tests follow the release history (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the current tree (`v2.8.0-rrule.2` activated), **When** the change-set tests run, **Then** they pass as today.
2. **Given** a STAGE change set for a next release whose rollback is the currently deployed release, **When** the tests run, **Then** they accept it and still check the inventory and rollback identity against that predecessor.
3. **Given** the historical first-cutover manifests and records, **When** the tests run, **Then** they remain checked and unmodified.

### Edge Cases

- `SCHEMA_INIT` stays a valid pre-upgrade ID.
- An expected count supplied as a non-integer, negative or missing value is a usage error.
- The previous successful activation markers for both earlier releases remain on disk.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | Requirement | Priority | Status | Delivery | No-op passable? |
|----|-------|-------------|----------|--------|----------|-----------------|
| FR-001 | Expected count is an input | As the operator, I want `build_release_baseline.py` to take the expected number of added migrations as a required, validated argument and pass it to `baseline.build`, so that the reviewed packet states the count instead of a constant. | High | Open | [build] | no |
| FR-002 | Builder fails closed | As Kent, I want the baseline build to fail with `GATE_MIGRATIONS_MISMATCH` when the observed added set's size differs from the expected count or a pre-upgrade ID is missing, so that a wrong qualification cannot be written. | High | Open | [build] | no |
| FR-003 | Verifier uses the reviewed baseline | As Kent, I want `verify_release_upgrade.py` to drop the constant and rely on the sha-bound baseline's `added_migration_ids`, so that acceptance checks exactly the reviewed set, including an empty one. | High | Open | [build] | no |
| FR-004 | Predecessor-aware change-set tests | As the operator, I want `test_vikunja_cutover_change_set.py` to derive the predecessor from the applied release history rather than the frozen first cutover, so that a STAGE whose rollback is `v2.8.0-rrule.2` passes while historical records stay checked. | High | Open | [build] | no |
| FR-005 | Tests for 10 and 0 | As Kent, I want tests covering a 10-migration and a 0-migration release through build, gate compare and verification, plus mismatch cases, so that both real releases are proven. | High | Open | [build] | no |
| FR-007 | Documentation synchronisation | As the operator, I want the architecture JSON and its markdown view, the cutover runbook, and INDEX and roadmap status kept consistent with the change, so that the docs describe the route. INDEX, roadmap and architecture need an update only if the implementer finds an entry affected; otherwise the WP records that none was. Added 2026-11-11 from analysis A1 (charter directive 5). | Medium | Open | [build] | no |
| FR-006 | Runbook | As the operator, I want `docs/runbooks/vikunja-release-cutover.md` to describe the count as the reviewed baseline's, so that the runbook matches the route. | Medium | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | No regression | 100% of existing `tests/deploy` and Vikunja script tests keep passing. | Reliability | High | Open |
| NFR-002 | Private evidence | 0 production rows in git and 0 new host paths; fixtures are synthetic; release-history records carry identity fields only, no paths (analysis A2, 2026-11-11). | Security | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | History untouched | Applied manifests, the committed `v2.7.1-670-420c7bcb75` baseline and `release.json` are not modified. | Technical | High | Open |
| C-002 | Fail closed | No change weakens a gate: every removed constant is replaced by a comparison against a reviewed input. | Technical | High | Open |
| C-003 | Merge and Office2 | The branch is pushed and a PR opened; Kent merges. No Office2 step. | Process | High | Open |
| C-004 | Review independence | Codex gpt-6.1-sol implements; a different model reviews, named with the date. | Process | High | Open |

## Success Criteria *(mandatory)*

- **SC-001**: A 0-migration fixture release builds a baseline, passes the gate compare and passes acceptance; a 10-migration fixture does the same. — [build] · no-op passable: no
- **SC-002**: Every mismatch case fails with its stable code. — [build] · no-op passable: no
- **SC-003**: The full test suite passes on the branch. — [build] · no-op passable: no

## Assumptions

- The baseline file is reviewed in the STAGE PR and bound by its sha in the release record, so its `added_migration_ids` is a reviewed input.

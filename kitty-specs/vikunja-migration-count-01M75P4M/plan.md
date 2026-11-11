# Implementation Plan: Vikunja release route takes the migration count from the release, not a constant

**Branch**: `fix/vikunja-migration-count` (planning base and merge target) | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary

Replace the hard-coded "exactly 10 added migrations" in the Vikunja release route with reviewed inputs. The baseline builder gets a required expected-count argument. The acceptance verifier relies on the sha-bound baseline's own `added_migration_ids`. The change-set tests derive the predecessor release from the applied history. Tests cover 10- and 0-migration releases and the mismatch cases. Engineering alignment: the design is settled by kentonium3/kg-automation#1098 and the lead's request, so no planning interview was held.

## Technical Context

**Language/Version**: Python 3.12 (stdlib only for Office2-deployed scripts), pytest.
**Primary Dependencies**: none new.
**Storage**: SQLite fixture databases built in temporary directories by the tests.
**Testing**: `tests/deploy/test_vikunja_release_baseline.py`, `test_vikunja_release_acceptance.py`, `test_vikunja_cutover_change_set.py`, the Vikunja script tests, then the full suite (`python -m pytest -q --ignore=docs/archive`) and `tooling/scripts/validate_docs.py`.
**Target Platform**: Office2 deploy scripts (run there only by the merged change sets); tests on Office4.
**Project Type**: existing automation repository.
**Performance Goals**: unchanged gate and preflight budgets.
**Constraints**: fail closed; history (applied manifests, committed baseline, `release.json`) untouched; stdlib only in deployed scripts; no production data.
**Scale/Scope**: 3 code sites, 1 test module's predecessor logic, new tests, 1 runbook line.

## Charter Check

| Gate | Status |
|---|---|
| Tests red-first for new behaviour | Pass: a 0-migration case fails today at each site. |
| Independent review | Pass: Codex gpt-6.1-sol implements; Claude Sonnet 5.5 reviews; Codex reviews the plan. |
| Changes by PR; merge is Kent's | Pass. |

## Design

- **D-1 Builder.** `baseline.build(pre, post, record, *, expected_added, deadline=None)`. The function raises `GATE_MIGRATIONS_MISMATCH` unless the pre-upgrade set is a subset of the post set and `len(added) == expected_added`. `build_release_baseline.py` gains a required `--expected-added-count N` (a non-negative int; anything else is `BUILD_BASELINE_USAGE`) and passes it through. Its own `!= 10` check is removed, because `baseline.build` now enforces the count. The count is a packet input, reviewed with the baseline in the STAGE PR.
- **D-2 Verifier.** Remove `len(facts["added_migration_ids"]) != 10` from `verify_release_upgrade.py`. The receipt binding already requires `receipt["baseline"] == facts`, and the baseline sha must match the release record. The `MIGRATIONS` check compares against `pre + added`. So an empty reviewed list is checked exactly, and any extra or missing migration fails.
- **D-3 Change-set tests.** Replace the frozen first-cutover predecessor in `_check_inventory` and `check_tree` with the release the current record's `rollback.ref` names. That release is found by matching an applied ACTIVATE manifest and its recorded release identity; `release.json` history is in git. Keep the existing assertions on the historical first-cutover manifests. Add a fixture-tree test for a STAGE whose rollback is `v2.8.0-rrule.2`.
- **D-4 Runbook.** Line 409 says the expected count is the reviewed baseline's.

## Implementation Concern Map

### IC-01 — Migration count from reviewed inputs

- **Purpose**: D-1 to D-4.
- **Relevant requirements**: FR-001 to FR-006; NFR-001, NFR-002; C-001, C-002.
- **Affected surfaces**: `scripts/deploy/vikunja_release/baseline.py`, `scripts/vikunja/build_release_baseline.py`, `scripts/vikunja/verify_release_upgrade.py`, `tests/deploy/test_vikunja_release_baseline.py`, `tests/deploy/test_vikunja_release_acceptance.py`, `tests/deploy/test_vikunja_cutover_change_set.py`, `docs/runbooks/vikunja-release-cutover.md`.
- **Sequencing/depends-on**: none.
- **Risks**: weakening a gate by deleting a check without replacing it (C-002); the change-set predecessor logic silently passing a wrong rollback identity.

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
- **D-3 Change-set tests (revised after the post-plan review).** The predecessor comes from a committed, data-free history record, not from git history: CI checks out shallow, and fixture trees have no history.
  - Add `services/vikunja/releases/<version>.json` for each release that has reached ACTIVATE. Each file holds that release's `release.json` as it was when activated, plus its `stage_issue` and `activate_issue`. Seed two: `v2.7.1-670-420c7bcb75` (STAGE and ACTIVATE `#1087`, from the frozen first-cutover record already in the test) and `v2.8.0-rrule.2` (STAGE and ACTIVATE `#1095`, from current `main`'s `release.json`).
  - The tests select the predecessor as the history entry whose `release_version` equals the current record's rollback version. They fail closed if no entry matches or more than one does. They then check the current record's rollback `image_id` against the predecessor's `image.config_digest`, its rollback archive against the predecessor's archive identity, and the inventory's `updated_by` against the predecessor's `activate_issue` for STAGE, or the current change set's issue for ACTIVATE.
  - The current change set's issue comes from its manifests, not a constant.
  - The frozen first-cutover checks on 0033 and 0034 stay as they are.
  - New fixture-tree tests: a STAGE to a next release with rollback `v2.8.0-rrule.2`; a new issue identity; a wrong rollback digest; a missing and a duplicate predecessor entry; a rollback that names an older applied release rather than the deployed one.
- **D-4 Runbook and CLI.** Update the builder command at runbook line 112 with `--expected-added-count N`. Explain how N is established: the number of migration IDs added in the Vikunja source between the rollback and release source revisions, recorded in the packet, and checked against the rehearsal's observed difference. Update line 409. CLI tests cover:
  - a missing, negative, non-integer or boolean count;
  - successes with 0 and 10;
  - a count mismatch, which writes no output;
  - an equal-schema zero-addition fixture matching `.2 → .3`, whose acceptance rejects both an extra ID and a lost predecessor ID.
- **D-5 Library boundary (EDGE, taken).** `baseline.build` rejects a non-`int` or boolean `expected_added`.
- **Retained assumption (EDGE, noted).** `rollback_release.py:325` keeps RRULE-specific `MIGRATION_OWNED_TABLES` and `MIGRATION_OWNED_COLUMNS`. They are unrelated to the count and still valid for rrule.3, which adds no tables or columns.

## Post-plan review, 2026-11-11

Codex gpt-6.1-sol (plan author Claude Opus 5.5): REQUEST CHANGES, 3 MATERIAL (D-3 provenance and issue identity, D-3 git-history dependency, D-4 runbook command and CLI tests), 2 EDGE. All five are folded above. The reviewer confirmed there are exactly three production ten-count checks, and that preflight, gate, activation and readiness accommodate zero additions.

## Implementation Concern Map

### IC-01 — Migration count from reviewed inputs

- **Purpose**: D-1 to D-4.
- **Relevant requirements**: FR-001 to FR-006; NFR-001, NFR-002; C-001, C-002.
- **Affected surfaces**: `scripts/deploy/vikunja_release/baseline.py`, `scripts/vikunja/build_release_baseline.py`, `scripts/vikunja/verify_release_upgrade.py`, `tests/deploy/test_vikunja_release_baseline.py`, `tests/deploy/test_vikunja_release_acceptance.py`, `tests/deploy/test_vikunja_cutover_change_set.py`, `services/vikunja/releases/` (new), `docs/runbooks/vikunja-release-cutover.md`.
- **Sequencing/depends-on**: none.
- **Risks**: weakening a gate by deleting a check without replacing it (C-002); the change-set predecessor logic silently passing a wrong rollback identity.

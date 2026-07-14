# Specification: gog credential post-publish cleanup

**Mission**: `gog-credential-post-publish-cleanup-01KXGMRP`
**Type**: software-dev
**Target branch**: `feat/731-gog-cred-post-publish-cleanup`
**Source**: kentonium3/kg-automation#731

## Purpose

Felix's credential-liveness probe (`scripts/security/credential_health_check/`)
and its gog re-auth helper (`scripts/security/gog-reauth.sh`) were built when the
Google OAuth app was in **External + Testing** publishing status, which forced a
hard 7-day refresh-token expiry. The app is now **published**, so that expiry no
longer applies to newly minted tokens. The probe's "routine 7-day Testing-app
cycle" classification and the re-auth script's operator guidance are now factually
wrong and risk masking a genuine future credential failure as "routine, just
re-mint." This mission removes those obsolete assumptions and the dead machinery
they depend on, and corrects the operator-facing guidance.

This is a **code + docs** mission. It does **not** touch the live OAuth token
(already re-minted and verified healthy 2026-07-14) or any Google Cloud Console
state.

## Background / Motivation

- Issue #731 documents four coupled defects, all rooted in the Testing→Published
  transition.
- The probe only classifies a credential dead **after** a real `invalid_grant`
  from `gog` — detection is correct; the *classification wording and the
  routine/unexpected split* are what became stale.
- The `#616` fix introduced a `reauth_marker_glob` baseline to distinguish
  "routine 7-day expiry" from "unexpected death." Post-publish there is no routine
  7-day expiry, so that entire distinction — and its baseline machinery — is dead
  code. The marker file it globs for was never created, so the machinery has in
  fact never functioned as intended (it always fell back to keyring mtime).

## Scope Decision (confirmed with operator)

**Collapse + delete.** Remove the routine/unexpected split so every dead token is
a single genuinely-unexpected "dead" classification, and delete the now-dead
`#616` baseline machinery (`_resolve_cycle_baseline`, `reauth_marker_glob`,
`CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`). Rationale: no gog account is in
External + Testing anymore (kentgale@gmail.com is published; internal Workspace
apps also do not carry the 7-day expiry), so the 7-day "routine" concept no longer
maps to reality. Aligns with the active-surface-hygiene and "migrations leave no
vestiges" engineering principles.

Explicitly **out of scope** (deliberate, may be revisited later): re-introducing
any testing-mode awareness for a hypothetical future External+Testing account. If
such an account is ever added, testing-awareness is re-added then.

## User Scenarios & Testing

### Scenario 1 — Post-publish token death (primary)
A published-app gog token is revoked or otherwise dies. The 6-hourly liveness
probe runs `gog ... calendar list`, receives `invalid_grant`, and files **one**
alert classified `dead` with an accurate reason (no "7-day" / "Testing-app"
language) and the correct recovery command. The operator re-auths; the next probe
reports the credential alive; the alert is resolved.

### Scenario 2 — Operator re-auth
The operator runs `gog-reauth.sh`. The script's guidance matches the **actual**
Google consent screen (ten scope checkboxes, not "six"), instructs the operator to
grant the personal-data scopes, and explicitly identifies the "See and download
your organization's Google Workspace directory" box as optional / decline-by-
default. On completion the script prints no claim of a "7-day expiry cycle" and no
"next forced re-auth in ~7 days" projection.

### Scenario 3 — Healthy token (unchanged)
The probe runs against a live credential, `gog` exits 0, the probe returns
"alive," and no alert is filed. Behavior is unchanged by this mission.

### Edge cases (unchanged behavior)
- Probe timeout (>15s) → `probe-error`.
- `gog` binary missing → `probe-error`.
- Non-`invalid_grant` non-zero exit → `probe-error`.
- A manifest entry that still carries `reauth_marker_glob` after removal → the
  field is no longer part of the schema; loader behavior for the removed key is
  defined by the plan (ignore-or-reject decided at plan time; must not crash the
  routine).

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The liveness probe classifies any dead OAuth credential (`invalid_grant`) as a single "dead" classification. The routine-vs-unexpected split is removed. | Draft |
| FR-002 | The dead-credential reason text contains no reference to a "7-day Testing-app cycle boundary," a 7-day TTL, or any expectation that token death is routine/expected. | Draft |
| FR-003 | The `#616` cycle-baseline machinery is deleted: `_resolve_cycle_baseline()`, the `reauth_marker_glob` config field, and the `CYCLE_WINDOW_HOURS` / `EXPECTED_TTL_DAYS` constants are removed from `liveness.py` and the manifest schema (`manifest.py`). | Draft |
| FR-004 | Every consumer that branches on the removed classifications (`orchestrator.py`, and any alert-writer that keys off classification) is updated so a dead credential still files exactly one alert with the correct recovery command and issue title/labels that no longer imply "routine." | Draft |
| FR-005 | The probe's failure/alive contract is preserved: returns `None` when alive; returns a `LivenessResult` on failure; probe-error paths (timeout, gog-missing, non-`invalid_grant` non-zero exit) are unchanged. | Draft |
| FR-006 | `gog-reauth.sh` header comments and closing summary no longer assert an External+Testing 7-day expiry cycle and no longer project a "next forced re-auth ~<date>" 7-day date. | Draft |
| FR-007 | `gog-reauth.sh` consent guidance accurately describes the real consent screen: the correct number of scope boxes, an instruction to grant the personal-data scopes, and explicit identification of the "organization's Google Workspace directory" box as optional / decline-by-default. | Draft |
| FR-008 | Architecture data and narrative docs are updated to match: `credential-manifest.json` drops the `reauth_marker_glob` config; `service-inventory.json` / `service-inventory.md` / `docs/INDEX.md` / the credential-liveness and google-workspace runbooks drop the "routine-7day" / "Testing-app cycle" framing. | Draft |
| FR-009 | The credential-liveness test suite (`tests/security/test_liveness.py`, `tests/security/test_orchestrator.py`) is updated to assert the single-dead-classification behavior and the absence of the removed machinery. | Draft |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The public probe entrypoint signature (`probe_oauth_liveness(credential, *, now_utc=None)`) and `LivenessResult` field set (minus the collapsed classification enum values) remain stable so no consumer needs a signature change. | Zero signature changes to `probe_oauth_liveness`; `LivenessClassification` reduced to exactly `{dead, probe-error}` (naming finalized at plan). | Draft |
| NFR-002 | The credential-liveness test suite passes and branch coverage is maintained. | `pytest tests/security/` green; `--cov-branch` coverage for the touched modules ≥ pre-change threshold. | Draft |
| NFR-003 | No change to probe cadence, timeout, or the `gog` invocation. | Timeout stays 15s; probe command args unchanged; systemd timer unchanged. | Draft |
| NFR-004 | No dead code referencing a 7-day cycle or the reauth marker remains in the probe module or manifest schema after the mission. | Grep for `reauth_marker_glob`, `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`, `_resolve_cycle_baseline`, `routine-7day`, `Testing-app` under `scripts/security/credential_health_check/` returns zero hits. | Draft |

## Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Rebaseline is **not required**: none of the touched paths match an audited surface in `audited-surfaces.json` (only `scripts/security/ssh-keys/*` under `scripts/security/` is audited; `credential_health_check/`, `gog-reauth.sh`, `credential-manifest.json`, docs, and tests are not). The mission/feat→main merge records `Rebaseline: not required — <reason>`. Deploy is by felix-deployer's `git pull origin/main` into the office2 checkout (the routine runs from `/home/claude/kg-automation` with `PYTHONPATH` = checkout root); **no `deploys/queued` manifest is needed** (no systemd/service/cron/out-of-checkout change). | Draft |
| C-002 | `kitty-specs/` and `.kittify/` are spec-kitty-managed; no manual edits outside workflow commands. | Draft |
| C-003 | Code + docs only. No re-minting or touching the live OAuth token; no Google Cloud Console changes. | Draft |
| C-004 | Change-risk tier: probe logic is Tier 3 (logic/workflow); it is also an audited surface, so the rebaseline obligation applies regardless of tier. | Draft |
| C-005 | The `7-day` string appears widely in unrelated surfaces (habits, vikunja token rotation, other runbooks). Only the credential-liveness / gog-reauth occurrences are in scope; unrelated occurrences must not be touched. | Draft |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | A dead credential produces exactly one alert whose reason contains no "7-day" or "Testing" language and includes the correct recovery command. |
| SC-002 | A healthy credential produces no alert (unchanged). |
| SC-003 | The re-auth script's operator output contains no 7-day-expiry claim, and its consent instructions match the actual number and identity of consent boxes, explicitly marking the directory box as optional/decline-by-default. |
| SC-004 | No probe-module or manifest-schema code references a 7-day cycle or a reauth marker (NFR-004 grep is clean). |
| SC-005 | The credential-liveness test suite passes with branch coverage maintained. |
| SC-006 | Architecture data/narrative docs and the two affected runbooks no longer describe a routine 7-day / Testing-app classification. |

## Key Entities

- **LivenessProbeConfig** (`manifest.py` dataclass; mirrored in
  `credential-manifest.json`): loses the `reauth_marker_glob` field.
- **LivenessResult / LivenessClassification** (`liveness.py`): classification enum
  collapses from `{dead-routine-7day, dead-unexpected, probe-error}` to
  `{dead, probe-error}` (final value name decided at plan).
- **credential-liveness-probe routine** (systemd user timer on office2, 6h):
  behavior unchanged except classification.
- **gog-reauth.sh**: operator re-auth helper; wording + consent guidance corrected.

## Assumptions

- The `kentgale@gmail.com` gog OAuth app is in published/production status; no gog
  account is intentionally kept in External+Testing. (If one is added later,
  testing-awareness is re-introduced then — out of scope now.)
- The live token was re-minted and verified healthy on 2026-07-14; this mission
  requires no live-credential action.
- Deploy to office2 for the probe change follows the existing mechanism by which
  `scripts/security/credential_health_check/` reaches the office2 checkout; the
  plan phase confirms the exact deploy path and any manifest entry needed.

## Out of Scope

- Re-introducing testing-mode awareness for a future External+Testing account.
- Auto-close of credential-liveness alert issues (tracked separately as future
  work in the original probe spec).
- Any change to the live OAuth token, its scopes, or GCP project configuration.
- The many unrelated `7-day` occurrences outside the credential-liveness / gog
  re-auth surfaces.

# Tasks: gog credential post-publish cleanup

**Mission**: `gog-credential-post-publish-cleanup-01KXGMRP`
**Branch**: `feat/731-gog-cred-post-publish-cleanup`

Small, tightly-coupled cleanup mission. 3 work packages. WP02 depends on WP01
(uses the collapsed `dead` classification value). WP03 is independent (parallel).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Collapse `LivenessClassification` to `{dead, probe-error}`; rewrite the `invalid_grant` branch to a single `dead` result; delete `_resolve_cycle_baseline`, `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`, unused imports | WP01 | |
| T002 | Remove `reauth_marker_glob` from `manifest.py` (`LivenessProbeConfig` field, `allowed_keys`, docstring, constructor) | WP01 | |
| T003 | Remove `reauth_marker_glob` config key from `credential-manifest.json` AND update its 7-day/Testing narrative fields for the gog credential | WP01 | |
| T004 | Rewrite `test_liveness.py`: delete marker/fallback tests, collapse timing tests to `invalid_grant → dead`, update keyring-missing → `dead`, keep alive/probe-error/UTC/disabled | WP01 | |
| T005 | `orchestrator.py`: unconditional investigate block; title prefix `credential-liveness-dead`; comment cleanup | WP02 | |
| T006 | `listing.py`: remove `expected_next_expiration` (field, `mtime+7d` computation, table column); keep `keyring_mtime_age`; drop unused `timedelta` import | WP02 | [P] |
| T007 | Update `test_orchestrator.py` for the single `dead` classification / new title | WP02 | |
| T008 | Update `test_listing.py` to drop `expected_next_expiration` assertions | WP02 | [P] |
| T009 | `gog-reauth.sh`: remove Testing/7-day header + "next forced re-auth ~7d" closing wording | WP03 | [P] |
| T010 | `gog-reauth.sh`: rewrite consent guidance to the real 10-box screen; mark org-directory box decline-by-default; drop "six boxes" | WP03 | [P] |
| T011 | `service-inventory.json`: drop routine-7day/Testing framing for the credential-liveness entry AND fix its stale `exec_start` (`credential_liveness_probe` → `credential_health_check`) | WP03 | |
| T012 | `service-inventory.md` + `docs/INDEX.md`: drop routine-7day/Testing framing | WP03 | |
| T013 | `docs/runbooks/credential-liveness-probe-ops.md` + `google-workspace-ops.md` + `calendar-helper-ops.md`: describe the single `dead` classification; drop 7-day/Testing framing | WP03 | |

## Work Packages

### WP01 — Probe classification collapse + schema + probe tests
- **Goal**: Collapse the liveness probe to a single `dead` classification and delete the `#616` baseline machinery + `reauth_marker_glob` schema/config; prove via rewritten `test_liveness.py`.
- **Priority**: MVP (core behavior)
- **Independent test**: `pytest tests/security/test_liveness.py` green; NFR-004 grep clean under `credential_health_check/`.
- **Dependencies**: none
- **Subtasks**:
  - [x] T001 Collapse classification + delete baseline machinery in `liveness.py` (WP01)
  - [x] T002 Remove `reauth_marker_glob` from `manifest.py` (WP01)
  - [x] T003 Remove `reauth_marker_glob` key + 7-day/Testing narrative from `credential-manifest.json` (WP01)
  - [x] T004 Rewrite `test_liveness.py` (WP01)
- **Risks**: manifest schema ↔ config atomicity (T002+T003 same WP/commit); preserve alive/probe-error paths.
- **Prompt**: `tasks/WP01-probe-classification-collapse.md` (~230 lines)

### WP02 — Alert construction + operator listing + their tests
- **Goal**: Update the alert writer to the single `dead` classification (unconditional investigate block, `credential-liveness-dead` title) and remove the fabricated `expected_next_expiration` from the `--list` view.
- **Priority**: MVP
- **Independent test**: `pytest tests/security/test_orchestrator.py tests/security/test_listing.py` green.
- **Dependencies**: WP01 (uses the `dead` classification value)
- **Subtasks**:
  - [ ] T005 `orchestrator.py` single-classification alert (WP02)
  - [ ] T006 `listing.py` remove `expected_next_expiration` (WP02)
  - [ ] T007 Update `test_orchestrator.py` (WP02)
  - [ ] T008 Update `test_listing.py` (WP02)
- **Risks**: dedup vs old issue titles handled out-of-band (IC-08, see Deploy notes); keep `--cov-branch`.
- **Prompt**: `tasks/WP02-alert-and-listing.md` (~220 lines)

### WP03 — Operator-facing text: gog-reauth.sh + docs
- **Goal**: Correct the re-auth script wording/consent guidance and the architecture/runbook docs to drop the obsolete 7-day/Testing framing.
- **Priority**: polish (no runtime logic)
- **Independent test**: greps in `quickstart.md` for `7-day`/`Testing`/`routine-7day` over the in-scope files return clean; script still runs its auth flow unchanged.
- **Dependencies**: none (parallel with WP01/WP02)
- **Subtasks**:
  - [ ] T009 `gog-reauth.sh` header/closing wording (WP03)
  - [ ] T010 `gog-reauth.sh` consent guidance rewrite (WP03)
  - [ ] T011 `service-inventory.json` framing + `exec_start` fix (WP03)
  - [ ] T012 `service-inventory.md` + `docs/INDEX.md` framing (WP03)
  - [ ] T013 runbooks: credential-liveness-probe-ops + google-workspace-ops + calendar-helper-ops (WP03)
- **Risks**: touch ONLY credential-liveness/gog occurrences; leave unrelated `7-day` strings (habits, vikunja, etc.) alone (C-005). Do not alter the script's auth flow — only comments/echo text.
- **Prompt**: `tasks/WP03-operator-text-and-docs.md` (~230 lines)

## Deploy / close-out notes (not a WP)

- **IC-08 (transitional dedup)**: Before/at `feat → main` deploy, close open old-titled
  liveness issues (currently #629 `credential-liveness-unexpected: gog-credentials-keyring`)
  so the new `credential-liveness-dead` prefix starts clean. Re-check the open set at close-out.
- **Deploy**: felix-deployer `git pull origin/main` into `/home/claude/kg-automation`;
  routine picks up on next 6h tick. No `deploys/queued` manifest.
- **Rebaseline**: not required (no audited surface).
- **Post-merge Codex review** of the full mission diff before `feat → main`.

## MVP scope

WP01 + WP02 deliver the runtime behavior change; WP03 is doc/text hygiene. All three
are in-scope for this mission.

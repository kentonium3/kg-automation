# Quickstart / Verification: Suppress expected drift alerts during rebaseline

How to build, test, deploy, and live-verify this mission.

## Unit tests (local, deterministic — covers FR-002/004/005, NFR-002)

`pytest` against `expected_drift.py` with an injected token path (via the
`EXPECTED_DRIFT_TOKEN_PATH` env override, or a `token_path` param mirroring
`rebaseline.read_token`):

| Case | Token fixture | `--list` output |
|------|---------------|-----------------|
| fresh + members | `expected_baselines:[X,Y]`, `pending_since_utc` = now | `X` and `Y` (newline-delimited) |
| stale (past short window) | same, `pending_since_utc` = 20 min ago | *(empty)* |
| absent | no file | *(empty)* |
| malformed | non-JSON bytes | *(empty)* |
| unparseable timestamp | `pending_since_utc` = "not-a-date" | *(empty)* |
| import failure | `rebaseline` import stubbed to raise | *(empty)*, exit 0 |

Exit code MUST be 0 in every case (the helper never fails its caller).

Run: `pytest scripts/deploy/felix-deployer/tests/test_expected_drift.py -v`
(or wherever the repo's felix-deployer tests live — match the existing rebaseline
test location).

## Deploy (Tier 3, manifest discipline)

1. Author `deploys/queued/drift-alert-rebaseline-suppression.yaml` mirroring applied
   `0022-systemd-unit-content-baseline.yaml`: `tier: 3`, `apply_mode: manifest`,
   `entrypoint: scripts/deploy/deploy-security-monitor-audit.py`,
   `audited_surface: false`, issue `kentonium3/kg-automation#862`.
2. Merge to main → felix-deployer self-pulls, runs the entrypoint (copies the updated
   `audit.sh` to `/data/services/security-monitor/scripts/audit.sh`), auto-commits the
   applied record. The new `expected_drift.py` arrives with the same self-pull
   (checkout-resident; no copy step).
3. **Rebaseline: not required** — `audit.sh` matches no audited-surfaces pattern; no
   hashed baseline drifts.

## Live verification on office2 (SC-001/002/003)

**Never write into the live felix-deployer state dir** — the running timer would race
it (Codex F4). Instead, put a synthetic token in a temp path and run the audit with
`EXPECTED_DRIFT_TOKEN_PATH=/tmp/verify-token.json`. felix-deployer's real state
(`/data/services/felix-deployer/state/`) is never touched (INV-1).

- **SC-001 (expected drift → push suppressed, but still detected)**: temp token names
  baseline `X`; force `X` to differ; run the audit with the env override; confirm the
  audit still **emits `[ALERT] X …` to stdout, exits 1, and writes the
  `drift-events.jsonl` event** (detection preserved — FR-008) but sends **no push** for
  `X`.
- **SC-002 (unexpected drift still pushes)**: temp token names `X`; force a DIFFERENT
  baseline `Y` to drift; confirm `Y` still pushes.
- **SC-003 (stale token pushes)**: set the temp token's `pending_since_utc` past the
  ~15 min window; confirm the drift on its named baseline pushes (no suppression).
- **Fail-safe spot check (FR-004)**: unset the env / no token; confirm any drift pushes
  exactly as before the change.
- **felix-deployer regression check (FR-008)**: confirm that with a *real* audited
  deploy, felix-deployer's reconcile still stamps the new baseline (applied-record
  `rebaseline: outcome: completed`) — i.e. the push suppression did not blind the
  rebaseline trigger.

Clean up all temp tokens/baseline perturbations after verification.

## Rollback

Revert the `audit.sh` change and re-run `deploy-security-monitor-audit.py` (or revert
the merge). The helper file is inert if `audit.sh` no longer calls it.

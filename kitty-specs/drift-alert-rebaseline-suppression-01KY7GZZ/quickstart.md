# Quickstart / Verification: Suppress expected drift alerts during rebaseline

How to build, test, deploy, and live-verify this mission.

## Unit tests (local, deterministic — covers FR-002/004/005, NFR-002)

`pytest` against `expected_drift.py` with an injected token path (the helper accepts a
`token_path` override, mirroring `rebaseline.read_token`):

| Case | Token fixture | `--list` output |
|------|---------------|-----------------|
| fresh + member | `expected_baselines:[X,Y]`, `pending_since_utc` = now | `X Y` |
| stale | same, `pending_since_utc` = 25 h ago | *(empty)* |
| absent | no file | *(empty)* |
| malformed | non-JSON bytes | *(empty)* |
| import failure | `rebaseline` import stubbed to raise | *(empty)*, exit 0 |

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

The audit only **reads** the token, so verification injects a synthetic pending token
(never touching felix-deployer's writer) and runs the read-only audit.

- **SC-001 (expected drift suppressed)**: write a synthetic
  `rebaseline-pending.json` naming a baseline and forcing that baseline to differ;
  run the read-only audit; confirm the audit **logs** the drift + writes the
  `drift-events.jsonl` event but sends **no** push (no `[ALERT]` for that baseline /
  `ALERT` unset). Remove the synthetic token afterward.
- **SC-002 (unexpected drift still pages)**: with a token naming baseline `X`, force a
  DIFFERENT baseline `Y` to drift; confirm `Y` still produces an `[ALERT]` / push.
- **SC-003 (stale token pages)**: set the synthetic token's `pending_since_utc` to
  > 24 h ago; confirm the drift on its named baseline pages (no suppression).
- **Fail-safe spot check (FR-004)**: remove the token entirely; confirm any drift
  pages exactly as before the change.

Clean up all synthetic tokens/baseline perturbations after verification; leave
felix-deployer state untouched (INV-1).

## Rollback

Revert the `audit.sh` change and re-run `deploy-security-monitor-audit.py` (or revert
the merge). The helper file is inert if `audit.sh` no longer calls it.

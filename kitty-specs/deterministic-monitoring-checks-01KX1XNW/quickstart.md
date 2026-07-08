# Quickstart: Deterministic Monitoring Checks — deploy & verify

**Mission**: deterministic-monitoring-checks-01KX1XNW
Deploy target: office2 (Ubuntu 24.04, `claude` systemd user). All agent SSH via
`ssh office2-claude`. python3-only.

## Pre-deploy (Mac / repo)

1. Merge the mission to `feat/deterministic-monitoring-checks`, then (after the
   mandatory post-merge Codex review) `feat → main`.
2. Confirm the deploy manifest `deploys/queued/<NNNN>-deterministic-monitoring-checks.yaml`
   is present and schema-valid.

## Deploy (via manifest pipeline, DIR-004) — STRICT ORDER (Codex #6)

Order matters to avoid a double-alert or missed-check window around 11:00/23:00:
**install units → smoke → enable timer → verify → remove crons → confirm**.

3. felix-deployer picks up the manifest within ~5 min of merge to main, installs
   `felix-health-check.{service,timer}` + the wrapper, and reloads the user daemon.
4. **Smoke** the service manually (before enabling the timer, before removing crons):
   ```
   ssh office2-claude 'systemctl --user start felix-health-check.service; systemctl --user status felix-health-check.service --no-pager | head'
   ```
5. **Enable** the timer and **verify** it is scheduled:
   ```
   ssh office2-claude 'systemctl --user enable --now felix-health-check.timer && systemctl --user list-timers felix-health-check.timer --no-pager'
   ```
6. **Only then remove** the two openclaw crons via CLI (DIR-007) — via the manifest
   script's vetted lib, or out-of-band:
   ```
   ssh office2-claude 'openclaw cron remove health-check-morning; openclaw cron remove health-check-evening'
   ```
7. **Confirm** no health-check cron remains:
   ```
   ssh office2-claude 'openclaw cron list 2>/dev/null | grep -i health || echo "no health-check cron (expected)"'
   ```

## Verify — heartbeat gate (no LLM in the hot path)

6. Force a tick and confirm zero tokens + correct routing:
   ```
   ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.openclaw.heartbeat_gate.run --dry-run'
   ```
   Expect `SUMMARY: outcome=… fallback=False … tokens=in:0(cache:0)/out:0`.
7. Confirm a real (non-dry-run) tick ledger entry has zeroed `gate_*_tokens`:
   ```
   ssh office2-claude 'tail -1 /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl'
   ```
8. Confirm no Haiku request appears in Anthropic spend attributable to the gate (console).

## Verify — escalation + fail-safe preserved

9. Escalation: a tick with a novelty marker / `HEARTBEAT.md` task / error still fires
   `openclaw system event` and records `outcome=ESCALATE_TO_SONNET`.
10. Fail-safe: point `--last-tick` at a corrupt/missing file and confirm
    `fallback_invoked=true` + escalation still fires.

## Verify — health-check (off the Sonnet agent) + delivery parity (Codex #5)

11. Confirm the check runs with **no main session** created:
    ```
    ssh office2-claude 'openclaw cron runs 2>/dev/null | grep -i health || echo "no health-check cron runs (expected)"'
    ```
12. Confirm healthy = silent (signal file stamped `ALL_HEALTHY`, no push):
    ```
    ssh office2-claude 'cat /data/services/openclaw/felix-health-check/last-run.json'
    ```
13. **Delivery parity** — force a `FAILURES_DETECTED` (or a `SCRIPT_MISSING`) and
    confirm the **ntfy push is actually received** with the full (bounded) output, and
    that `UNKNOWN`/non-zero/missing-script all alert. Confirm an ntfy send failure is
    recorded (journal + signal file `delivery` field), not silently swallowed.
    (ntfy topic must be configured — mirror `security-monitor` `NTFY_TOPIC`.)

## INV-006 validation (verify-before-done)

13. Replay the deterministic rule over the live ledger — must be 0 missed:
    ```
    ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.openclaw.heartbeat_gate.validate_ledger --ledger /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl'
    ```
    Expect `MISSED escalations: 0` and the over-escalation rate reported (≤5%).

## Rebaseline (#557)

14. The change touches systemd user units + deploy scripts (pipeline-rebaselined by
    felix-deployer if applied via manifest) **and** openclaw config (cron removal). If
    the cron removal is out-of-band, rebaseline manually per
    `docs/runbooks/security-baseline-ops.md`:
    ```
    ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
    ```
15. Record `Rebaseline: completed at <ts>` (or `not required — <reason>`) in the merge
    commit.

## Post-deploy watch

16. Over ~7 days, confirm Anthropic spend attributable to heartbeat-gate + health-check
    trends toward ~$0 (target ~$15–20/mo saved, NFR-003).
17. No new errors in the heartbeat + health-check logs for 24 h.

## Rollback

Revert the merge commit + redeploy prior state (felix-deployer re-applies the previous
systemd/openclaw config); re-add the two `health-check-*` crons; the prior Haiku gate
returns. No data migration involved. Rebaseline after rollback.

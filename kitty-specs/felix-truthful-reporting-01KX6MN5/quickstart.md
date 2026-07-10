# Quickstart: Felix Truthful Reporting Guardrails

**Mission**: felix-truthful-reporting-01KX6MN5

How to run, deploy, and verify the truthful-reporting guardrails.

## What ships

1. **Doctrine** — truthful-reporting + mechanism-fidelity block in all 7 fleet
   agent prompts; no-unrequested-infrastructure block in `main`.
2. **Detector** — `scripts/trust/` package + a single timer entrypoint
   (`run_trust_scan`) that runs a cron-drift scan and an assertion-verification
   scan, alerting via the #701 bus.
3. **Baseline** — `docs/design/architecture/data/approved-crons.json` (the
   allowlist of legitimate crons).
4. **Deploy** — `deploys/queued/NNNN-truthful-reporting-detector.yaml` +
   `scripts/deploy/deploy-truthful-reporting.py` (installs the systemd user
   timer, runs a `--dry-run` self-test).

## Local development / test

```
# Unit + acceptance tests (deterministic; OpenClaw/Vikunja/bus mocked)
python3 -m pytest tests/trust -v --cov=scripts/trust --cov-branch

# Dry-run the scan locally (no alerts, no state mutation)
python3 -m scripts.trust.run_trust_scan --dry-run --json
```

## Deploy to office2 (post-merge, operator-run)

> Follows the #701/#699 deploy lessons. Do **not** hand-crank on office2.

1. Merge the mission to `fix/felix-truthful-reporting`, run the **post-merge
   Codex review** of the full diff, fold fixes, then merge `fix → main`.
2. felix-deployer picks up `deploys/queued/NNNN-truthful-reporting-detector.yaml`
   on its next tick and runs the entrypoint, which:
   - installs `felix-trust-scan.timer` + `.service` (user units under `claude`),
   - `systemctl --user daemon-reload` + `enable --now`,
   - runs `run_trust_scan --dry-run --json` as a preflight self-test,
   - reports via the #701 bus.
3. **Rebaseline** (audited surface): the AGENTS.md prompt changes touch an
   audited surface. On the pipeline happy path felix-deployer rebaselines
   automatically after the committed prompt change is confirmed; verify the
   `rebaseline:` stamp on the applied YAML record. If out-of-band, reset
   baselines manually per `docs/runbooks/security-baseline-ops.md`.
4. The merge commit records `Rebaseline: completed at <ts>` (or
   `Rebaseline: not required — <reason>` for the non-prompt WPs).

## Verify live (SC-001..005)

- **SC-004** — confirm doctrine present:
  ```
  grep -l "report .*only .*performed\|mechanism" scripts/openclaw/agents/*/AGENTS.md
  ```
- **SC-001/002** — regression: DM `main` "create a Vikunja todo to remind me to
  run X daily"; confirm the Vikunja task(s) exist, `openclaw cron list` shows no
  new cron, and the reply claims only what was done.
- **SC-003** — inject a throwaway cron (`openclaw cron add …` for a name not in
  the baseline) and a bogus assertion (nonexistent Vikunja id); run
  `run_trust_scan --once`; confirm two alerts hit Kent's phone within a cycle;
  then remove the throwaway cron.
- **SC-005** — point the baseline path at an unreadable file; run
  `run_trust_scan --json`; confirm `ok:false`, exit 2, **no** alert, agents
  unaffected.

## Rollback

- Detector: disable the timer (`systemctl --user disable --now
  felix-trust-scan.timer`) — agents are unaffected (out-of-band).
- Doctrine: revert the AGENTS.md commits + re-sync prompts + rebaseline.

## Key gotchas folded in (from #701/#699/#706)

- Deploy entrypoint must be `chmod +x`; it must **install + daemon-reload**
  units (a repo unit file does nothing until installed).
- A failing manifest left in `deploys/queued/` fail-loops felix-deployer with an
  alert every tick — get the entrypoint right before merge.
- office2 is `python3`-only; invoke as `python3 -m scripts.trust.<mod>`.
- Fail-safe everywhere: a detector fault must never break an agent.

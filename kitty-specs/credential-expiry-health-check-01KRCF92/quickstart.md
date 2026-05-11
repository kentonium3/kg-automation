# Quickstart — Credential Expiry Health Check

**Mission**: `credential-expiry-health-check-01KRCF92`
**Audience**: Kent (operator), future Felix agents that may need to redeploy this check.

This document describes how to deploy the check the first time, how to verify it, and how to inspect its operational state day-to-day.

---

## Initial deploy (one-time, by Kent)

The deploy procedure follows the felix-doc-auditor precedent (#223). All steps run as the `claude` user on office2 — no sudo required.

### 1. Land the merged changes on office2

```bash
ssh office2-claude
cd /home/claude/kg-automation
git pull origin main
```

### 2. Run the deploy script

```bash
bash scripts/office2/deploy/credential-health-check.sh
```

The script:

- Copies `scripts/office2/credential-health-check.{timer,service}` to `~/.config/systemd/user/`
- Runs `systemctl --user daemon-reload`
- Enables and starts the timer: `systemctl --user enable --now credential-health-check.timer`

### 3. Verify the timer is armed

```bash
systemctl --user list-timers --all | grep credential-health-check
```

Expected: a row showing `credential-health-check.timer` with `Next:` set to the next 13:00 UTC.

---

## First-run canary (validates the alert path end-to-end)

Before letting the auditor run unsupervised against the live manifest, run the canary procedure:

### A. Synthetic-fixture canary (preferred)

1. On office2 as `claude`:
   ```bash
   cd /home/claude/kg-automation
   python3 scripts/security/credential-health-check.py \
     --manifest tests/fixtures/manifest-near-expiry.json \
     --dry-run-issue-prefix 'CANARY: Credential review:'
   ```
   The `--dry-run-issue-prefix` flag swaps the title prefix so the canary's issues don't collide with future real alerts. (If this flag isn't supported in v1, use a separate test repo or branch.)
2. Verify exactly one GitHub issue is created with title `CANARY: Credential review: <name> due <date>`.
3. Verify exactly one Vikunja task is created with title `Rotate credential: <name>` and `due_date` exactly 7 days before the boundary.
4. Inspect cross-references in both directions (issue body → task URL; task description → issue URL).
5. Close the canary issue and complete the canary task. Then re-run with the same fixture; verify NO new artefacts are created (dedup works).

### B. Manual trigger of real cycle (after canary A passes)

```bash
systemctl --user start credential-health-check.service
```

Wait ~10 seconds. Then:

```bash
journalctl --user -u credential-health-check --since "1 minute ago"
```

You should see a clean `cycle_start` → per-credential evaluations → `cycle_end` trace. With the current manifest (as of 2026-05-11), no credentials should be inside the 30-day warning window, so no real alerts should fire.

---

## Day-2 operations

### Inspect the most recent cycle

```bash
journalctl --user -u credential-health-check --since today
```

Or for the latest cycle only:

```bash
journalctl --user -u credential-health-check -n 100 --no-pager
```

### Run an ad-hoc check (outside the timer schedule)

```bash
systemctl --user start credential-health-check.service
```

The service is `Type=oneshot`; it runs once and exits. The timer's next scheduled run is unaffected.

### Soft-kill (disable the auditor only)

```bash
systemctl --user stop credential-health-check.timer
systemctl --user disable credential-health-check.timer
```

Re-enable with:

```bash
systemctl --user enable --now credential-health-check.timer
```

### Inspect what the auditor would do without filing anything

Run with a `--dry-run` flag (if supported in v1):

```bash
python3 scripts/security/credential-health-check.py --dry-run
```

This prints the decisions to stdout without writing GitHub issues or Vikunja tasks.

---

## When an alert fires

When you receive the email notification + see the Vikunja task:

1. **Read the GitHub issue body** — it carries the full rotation procedure from `credential-manifest.json` `expiry_notes`.
2. **Rotate the credential** following the procedure.
3. **Update `last_reviewed`** in `docs/design/architecture/data/credential-manifest.json` to today's date.
4. **Commit + push** the manifest change.
5. **Close the GitHub issue** with a comment referencing the commit hash.
6. **Mark the Vikunja task done.**

The next daily run will see the credential as fresh and will not re-alert.

---

## When the auditor fails

The timer keeps firing daily even if the service exits non-zero. Symptoms:

- Email from GitHub never arrives for a known-near-cadence-boundary credential
- `systemctl --user status credential-health-check.service` shows `failed` state
- `journalctl --user -u credential-health-check` shows tracebacks or "ManifestUnreadableError"

Recovery is to fix the root cause (most commonly: someone broke the manifest JSON). Re-running manually with `systemctl --user start credential-health-check.service` validates the fix.

If the auditor's own `kg-felix-bot-pat` is the credential that's about to expire (see edge case in spec §6), Kent needs to rotate it manually before the warning window closes; the auditor will not be able to self-alert if the PAT is already broken.

---

## Decommission

If the auditor needs to be retired:

1. Stop and disable: `systemctl --user disable --now credential-health-check.timer`
2. Remove the user-systemd units: `rm ~/.config/systemd/user/credential-health-check.{timer,service}`
3. `systemctl --user daemon-reload`
4. Remove the entry from `service-inventory.json` and `service-inventory.md`
5. Remove the cross-reference from `credentials-and-secrets.md`

The script itself can be retained in the repo (no harm) or removed in the same change.

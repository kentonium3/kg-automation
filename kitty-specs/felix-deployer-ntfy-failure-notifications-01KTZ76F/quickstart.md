# Quickstart: Felix-deployer ntfy Failure Notifications

End-to-end walkthrough of installing, exercising, and verifying the fixed felix-deployer notification path. Operator-facing. Run after this mission merges to main.

---

## Prerequisites

- Mission merged to `main`. Merge commit recorded `Rebaseline: completed at <ts>` per #557.
- `ssh office2-claude` reachable.
- Mac checkout on `main` synced past the merge commit.
- The ntfy phone app installed and signed in (one-time setup; not in mission scope).

---

## Step 1 — Pull the fix on office2

The applier ticks every 5 min and `git fetch + reset --hard origin/main` is part of the tick loop. Wait one tick after merge (≤5 min), OR force-pull immediately:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git fetch origin && git reset --hard origin/main && git log -1 --oneline'
```

Confirm the merge commit SHA matches.

---

## Step 2 — Mint a topic and write the env file on office2

The topic is a private path segment for ntfy.sh. Choose a hard-to-guess suffix:

```bash
ssh office2-claude 'mkdir -p ~/.config/felix-deployer && cat > ~/.config/felix-deployer/env <<EOF
FELIX_DEPLOYER_NTFY_TOPIC=felix-deployer-$(openssl rand -hex 6)
EOF
chmod 0640 ~/.config/felix-deployer/env'
```

Read back the topic:

```bash
ssh office2-claude 'grep -h "^FELIX_DEPLOYER_NTFY_TOPIC=" ~/.config/felix-deployer/env'
```

Copy the suffix (everything after `felix-deployer-`) and subscribe your ntfy app to `felix-deployer-<that-suffix>`.

---

## Step 3 — Roll back the broken applier

The current applier on office2 still has the broken notify.py path. Stop and remove its units:

```bash
cd /Users/kentgale/repos/kg-automation
./scripts/deploy/deploy-felix-deployer-bootstrap.sh --rollback
```

Verify the units are gone:

```bash
ssh office2-claude 'systemctl --user list-unit-files felix-deployer.* || echo "(no units)"'
```

---

## Step 4 — Re-apply the fixed bootstrap

```bash
./scripts/deploy/deploy-felix-deployer-bootstrap.sh --apply
```

Expected steps in the log (note: only 6 steps total; the broken step-5 openclaw cron registration is removed):
1. Pre-flight: openclaw cron healthy
2. rsync repo to remote
3. Install systemd user units (felix-deployer.service + .timer)
4. systemctl --user daemon-reload
5. systemctl --user enable --now felix-deployer.timer
6. Post-flight: confirm timer active
7. Write `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`; commit + push from office2

(If the script keeps the original 7-step header text but logs only 6 actions, that's expected — the previously-broken step-5 slot is removed entirely, not replaced with a no-op.)

---

## Step 5 — Verify the fixed applier is live

```bash
ssh office2-claude 'systemctl --user is-active felix-deployer.timer && systemctl --user list-timers felix-deployer.timer --no-pager'
```

Expect: `active` and a NEXT timestamp ≤5 min in the future.

Confirm the env file is loaded:

```bash
ssh office2-claude 'systemctl --user show felix-deployer.service -p EnvironmentFiles'
```

Expect: `EnvironmentFiles=/home/claude/.config/felix-deployer/env (ignore_errors=yes)`.

---

## Step 6 — Smoke test: deliberate failure produces an ntfy push

Queue a manifest that's guaranteed to fail at the entrypoint phase:

```bash
cd /Users/kentgale/repos/kg-automation
cat > deploys/queued/smoke-test-deliberate-fail.yaml <<'EOF'
schema_version: v1
name: smoke-test-deliberate-fail
issue: kentonium3/kg-automation#595
tier: 3
entrypoint: scripts/deploy/deploy-this-script-does-not-exist.sh
audited_surface: false
created_at: "<run date +%Y-%m-%dT%H:%M:%SZ>"
created_by: operator-smoke
EOF
git add deploys/queued/smoke-test-deliberate-fail.yaml
git commit -m "test: deliberate smoke failure for #595 verification"
git push
```

Wait one applier tick (≤5 min). Observe:
- Your phone gets an ntfy push with title `felix-deployer failed: smoke-test-deliberate-fail`.
- Body includes `Phase: entrypoint`, the tier, the head SHA prefix, the failed-at timestamp, and an error summary referencing the missing script.
- On office2: `ls deploys/failed/smoke-test-deliberate-fail/` shows the failure artifact.
- `deploys/queued/smoke-test-deliberate-fail.yaml` is no longer queued.

Clean up:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && rm -rf deploys/failed/smoke-test-deliberate-fail && git add -A && git commit -m "chore: clear smoke-test failure record" && git push'
```

(Run the cleanup from office2 so the git config matches the applier's expected identity.)

---

## Step 7 — Rebaseline (operator action, per #557)

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

Expect: `Security audit YYYY-MM-DD: All clear` and 14 fresh baseline files.

---

## Step 8 — Close out

- Close issue #595 with a comment referencing the merge commit + the successful smoke push.
- If you skipped the deliberate-failure smoke test, file a follow-up to do it later — the redaction+truncation invariant has only been tested via unit tests until you exercise the live path.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `--apply` step 5 (enable timer) fails | Stale .service/.timer files from broken bootstrap | Re-run `--rollback`, then `--apply` |
| Push received but body shows `Error: (no error summary)` | Manifest's failing script wrote nothing to stderr | Expected; the artifact in `deploys/failed/` carries the full log |
| Push received but topic in app doesn't get it | env file path mismatch | `systemctl --user show felix-deployer.service -p EnvironmentFiles` and verify the path is `/home/claude/.config/felix-deployer/env` |
| No push received, applier shows failure | Topic env not loaded OR network failure | Check `journalctl --user -u felix-deployer.service \| grep -i ntfy` for `NTFY_*` error_code |
| `journalctl` shows `NTFY_MISSING_TOPIC` | env file empty or unset | Re-run Step 2 |
| `journalctl` shows `NTFY_CURL_MISSING` | curl not on PATH for systemd user session | `which curl` on office2; verify systemd user `PATH` includes `/usr/bin` |

# Quickstart: OpenClaw Skills Deploy/Sync

Deploy + live-verify runbook for mission `openclaw-skills-sync-01KXW1DQ` (#775). Authoritative for
the mission's task-6 deploy step. Full ops runbook ships as `docs/runbooks/agent-skill-sync-ops.md`.

## Local sanity (Mac / any checkout)

```
# Dry-run drift preview against the LOCAL deployed dir is not meaningful on Mac
# (no /home/claude/.openclaw). Run the unit + integration suite instead:
python3 -m pytest tests/openclaw/deploy/test_deploy_agent_skills.py -v
```

## Deploy (office2) — via the manifest pipeline

The mechanism deploys through `deploys/queued/skills-sync.yaml`. After the mission merges to `main`:

1. **Code + units arrive automatically** in the shared checkout `/home/claude/kg-automation` via
   the checkout's own self-advance (felix-deployer / agent-prompt-sync tick pulls `origin/main`).
2. **felix-deployer applies the manifest** (`deploys/queued/skills-sync.yaml`) within ~5 min: its
   entrypoint `scripts/deploy/deploy-skills-sync.sh` pre-flights, verifies the helper + unit files
   are present, copies `agent-skill-sync.{service,timer}` into `~/.config/systemd/user/`, then runs a
   **hard verify-before-enable gate** (`XDG_RUNTIME_DIR` exported): `daemon-reload` → smoke
   (`systemctl --user start agent-skill-sync.service`, assert `skills-last-tick.json` written) →
   `enable --now` → assert `is-enabled` + `list-timers`. A failed smoke/enable **fails the deploy
   loudly** — an installed-but-not-running timer is not accepted as applied.

## Live-verify (office2, as claude — task 6)

Run with the user session bus exported (non-login ssh shows `--user` as `degraded`):

```
ssh office2-claude
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# 1. Confirm the timer is enabled + active (enable here if the manifest left it best-effort):
systemctl --user daemon-reload
systemctl --user enable --now agent-skill-sync.timer
systemctl --user list-timers | grep agent-skill-sync

# 2. Dry-run — expect the currently-drifted skills listed, nothing written:
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_skills --dry-run

# 3. Force one real tick, then confirm convergence (deployed MD5 == repo MD5 for all 6):
systemctl --user start agent-skill-sync.service
for s in doc-audit escalation skill-author task-intelligence vikunja-api whisper; do
  r=$(md5sum scripts/openclaw/skills/$s/SKILL.md | cut -d" " -f1)
  d=$(md5sum /home/claude/.openclaw/skills/$s/SKILL.md | cut -d" " -f1)
  [ "$r" = "$d" ] && echo "OK  $s" || echo "DRIFT $s"
done

# 4. Audit + freshness signals present:
tail -n 3 /data/services/openclaw/deploy/agent-skill-sync.jsonl
cat /data/services/openclaw/deploy/skills-last-tick.json   # exit_code 0, recent completed_at_utc

# 5. Independent drift check surfaces an induced divergence + orphans, ignores *.backup*:
python3 -m scripts.openclaw.enforcement.skills_drift_check --json   # exit 0 = clean
#    (edit a deployed SKILL.md out-of-band → expect it flagged as drift; a *.backup* is not;
#     a deployed skill with no repo dir is flagged as an orphan — alert-only, not deleted)
```

## Rebaseline (audited surface — C-002)

New systemd unit + deploy script are an audited surface. On the felix-deployer happy path the
auto-rebaseline (#685 watermark) covers it once the expected drift is confirmed; the merge commit
records `Rebaseline: completed at <ts>` (or `not required — <reason>`) per
`docs/runbooks/security-baseline-ops.md`. Verify `audited-surfaces.json` globs match the new unit +
`scripts/deploy/deploy-skills-sync.sh`; extend if not.

## Rollback

Additive mechanism — to reverse:
```
systemctl --user disable --now agent-skill-sync.timer
rm -f ~/.config/systemd/user/agent-skill-sync.{service,timer}
systemctl --user daemon-reload
# remove deploys/queued/skills-sync.yaml, revert the deploy-module commit
```
Deployed `SKILL.md` files already synced remain in place (copy-only). No service depends on the sync
existing; its absence returns to the prior manual-only state.
```

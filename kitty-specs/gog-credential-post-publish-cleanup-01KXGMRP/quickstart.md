# Quickstart / Verification: gog credential post-publish cleanup

## Local (pre-merge)

Run the affected test suite with branch coverage:

```
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/security/test_liveness.py tests/security/test_orchestrator.py -v
```

Static checks that the removed machinery is gone (should print nothing):

```
grep -rnE "reauth_marker_glob|CYCLE_WINDOW_HOURS|EXPECTED_TTL_DAYS|_resolve_cycle_baseline|routine-7day|Testing-app" scripts/security/credential_health_check/
```

Confirm `gog-reauth.sh` no longer claims a 7-day cycle (should print nothing):

```
grep -nE "7-day|Testing|Next forced re-auth|six scope" scripts/security/gog-reauth.sh
```

Confirm the manifest config dropped the key (should print nothing):

```
grep -n "reauth_marker_glob" docs/design/architecture/data/credential-manifest.json
```

## Post-deploy (after feat/731 → main)

1. Confirm the office2 checkout advanced past the merge:
   ```
   ssh office2-claude 'git -C /home/claude/kg-automation log --oneline -1'
   ```
2. Trigger a probe cycle and confirm a healthy credential still reports alive (the
   live token is healthy, so this should log `credential_alive`, not a dead alert):
   ```
   ssh office2-claude 'systemctl --user start credential-liveness-probe.service'
   ssh office2-claude 'journalctl --user -u credential-liveness-probe.service --since "2 minutes ago" | grep -E "credential_alive|credential_dead"'
   ```
3. (Optional negative check) The new classification path only fires on a real
   `invalid_grant`; do not force one. The unit tests cover the dead path.

## Success mapping

- SC-001/SC-004 → the two `grep` checks above return clean; unit tests assert the
  single `dead` classification and clean reason text.
- SC-002 → step 2 logs `credential_alive` (no alert) for the healthy token.
- SC-003 → `gog-reauth.sh` grep is clean and the consent step names the directory box.
- SC-005 → pytest green with `--cov-branch` maintained.
- SC-006 → docs greps for `routine-7day` / `Testing-app` under the in-scope docs are clean.

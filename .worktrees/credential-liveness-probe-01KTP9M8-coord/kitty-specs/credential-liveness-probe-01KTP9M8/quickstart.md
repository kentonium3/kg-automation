# Quickstart — Credential Liveness Probe

**Mission**: `credential-liveness-probe-01KTP9M8`
**Phase**: 1 — Design

This document describes how the probe operates day-to-day after this mission lands. It's the manual a new operator (or future-me) reads to understand the surface.

## The 30-second mental model

1. Every 6 hours, a systemd timer on office2 fires the liveness probe.
2. For each `oauth2` credential opted-in via the manifest, the probe makes one cheap `gog calendar list` call.
3. Exit 0 → credential is alive. Done. No issue. No noise.
4. `invalid_grant` → credential is dead. The probe classifies whether it's the routine 7-day cycle or an unexpected revocation, files a GitHub issue with the exact recovery command, and stops.
5. You see the issue (via GitHub UI, digest, or downstream WhatsApp pipeline), run the recovery command, and manually close the issue.
6. Next 6h cycle → probe sees alive → no new issue. The old issue stays open as your audit trail until you close it.

## The recovery command

For the gog default account (`kentgale@gmail.com`):

```
ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh
```

Takes ~3 minutes. Most of it is browser-side consent. The script handles env vars, paths, services list, post-auth liveness check, and tells you the next forced-re-auth date.

## How to check the probe yourself (no waiting for the timer)

From any shell on office2 as claude:

```
PYTHONPATH=/home/claude/kg-automation/scripts/security python3 -m credential_health_check --dry-run --liveness-only
```

Outputs structured log lines. Look for `credential_alive` (good) or `credential_dead` with a classification field. `--dry-run` ensures NO GitHub issue is filed even if dead.

Or, fire the systemd unit directly:

```
systemctl --user start credential-liveness-probe.service
journalctl --user -u credential-liveness-probe.service --since "1 minute ago"
```

This is the real probe (not dry-run); if dead, a GH issue will be filed.

## Interpreting the classification

| Classification | What it means | What to do |
|---|---|---|
| `dead-routine-7day` | Token expired on schedule (within ±24h of mtime + 7d). Expected. | Run `gog-reauth.sh`. Close the GH issue when done. |
| `dead-unexpected` | Token died at non-cycle time. Could be password change, manual revoke at myaccount.google.com/permissions, or Google security review. | Check https://myaccount.google.com/permissions FIRST (verify the app is still authorized). Then run `gog-reauth.sh`. Close the GH issue. |
| `probe-error` | Probe itself failed (timeout, gog binary missing, network down). Credential state is unknown. | Check the GH issue's `reason` field; address the underlying probe-error. No re-auth needed unless a follow-up probe shows `dead-*`. |

## How to add a new oauth2 credential to liveness monitoring

For a future Workspace-internal migration (Option A in `reference_gog_credential_health_gap.md`):

1. Add the credential record to `docs/design/architecture/data/credential-manifest.json` with the new `liveness_probe` block (per `contracts/manifest-liveness-probe-block.md`).
2. Run the deploy script: `bash /home/claude/kg-automation/scripts/office2/deploy/credential-liveness-probe.sh`.
3. The next 6h cycle will probe the new credential alongside the existing one.

No code change needed. The probe iterates all credentials with `liveness_probe.enabled is true`.

## How to disable the probe temporarily

Set `liveness_probe.enabled: false` in the credential record, commit, deploy. The credential stays configured but the probe skips it.

Or stop the timer entirely: `systemctl --user disable --now credential-liveness-probe.timer`. The next probe cycle won't fire until you re-enable.

## How to invoke the recovery from your phone

Phone-recovery acceptance gate per FR-021 + SC-11. Walk-through:

1. Open Termius on your phone.
2. Connect to the `office2-claude` host (Tailscale routes you to it).
3. Type: `/home/claude/kg-automation/scripts/security/gog-reauth.sh`. Press Enter.
4. The script prints a Google authorization URL. **Tap-and-hold the URL to copy it**, or tap it directly to open in mobile Safari.
5. In Safari: sign in as `kentgale@gmail.com`. Click through "Advanced → Continue (unsafe)". **Check ALL six scope boxes**. Continue.
6. Safari shows a `http://localhost:...?state=...&code=...` "site can't be reached" page. Tap the URL bar, select-all, copy.
7. Switch back to Termius. The script is waiting at a `read -r` prompt. Paste the URL. Press Enter.
8. The script runs step 2 + liveness probe. You should see `OK: gog calendar API is live`.
9. Close the corresponding GH issue (from the GitHub mobile app or web).

Time on phone: ~5 minutes including app-switching. Slightly longer than Mac (~3 minutes) but works.

## When this probe will surface a problem you can't fix from your phone

- Probe itself is broken (e.g., gog binary removed, env var unset on office2): you'll see `classification: probe-error` in the issue. Re-auth won't help. The systemd service or office2 itself needs attention. This is rare; if it happens, escalate via the normal infra channel.
- Refresh token revoked AND the OAuth client_secret on office2 has also been compromised: the runbook's full §2.8 setup applies, not just `gog-reauth.sh`. Rare.
- Tailscale itself is down: can't ssh in. Tailscale's own credential-health-check (existing signal, not new) would have already filed an issue for this. Address Tailscale first.

## What this probe does NOT do

- Does NOT predict future expirations (e.g., "expires in 24h"). The probe is reactive; you'll see the failure within 6h of when it actually happens.
- Does NOT attempt to re-mint tokens autonomously. Operator action required.
- Does NOT close the issue when probe succeeds again (auto-close is Future Work in spec.md).
- Does NOT touch the existing daily `credential-health-check.timer` cadence or signals.
- Does NOT emit WhatsApp pings directly — downstream digest reads the GH issue and decides.

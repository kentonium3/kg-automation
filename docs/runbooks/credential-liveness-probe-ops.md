---
title: Credential Liveness Probe Operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-06-16
last_validated: 2026-06-16
last_updated: '2026-06-16'
version: v1.0
owners: [kgale]
---

# Credential Liveness Probe Operations

The `credential-liveness-probe` is one of two periodic configuration-integrity
sweeps on office2. Every 6 hours it probes each OAuth credential in the
manifest with a live API call; when a credential dies, it auto-files a
GitHub issue with the recovery command in the body. The sister sweep is
the daily [Security Baseline Audit](<./security-baseline-ops.md>) at 3 AM,
which detects unexpected drift in the system's configuration surface.

This runbook is the canonical surface for the probe. Service-specific
runbooks (e.g. [google-workspace-ops](<./google-workspace-ops.md>)) link here
for the probe's behavior and only document service-specific recovery details.

Tracking issues: original implementation #572; today's classification-baseline
fix #616.

---

## Locations

| Surface | Path on office2 |
|---|---|
| Probe entrypoint | `/usr/bin/python3 -m scripts.security.credential_health_check --liveness-only` |
| Manifest consumed | `/home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json` |
| Source code | `scripts/security/credential_health_check/` (in repo) |
| Liveness logic | `scripts/security/credential_health_check/liveness.py` |
| Systemd timer | `~/.config/systemd/user/credential-liveness-probe.timer` |
| Systemd service | `~/.config/systemd/user/credential-liveness-probe.service` |
| Logs | `journalctl --user -u credential-liveness-probe.service` |

Spec authority:
[`kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md`](<../../kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md>).

---

## Cadence

`OnCalendar=*-*-* 00,06,12,18:00:00 UTC` — four times per day at UTC midnight,
06:00, 12:00, 18:00. The probe completes per-credential in well under a
second (the live API call timeout is 15 s; a real network round-trip is
~500–900 ms).

---

## What the probe does, per credential

For each manifest entry whose `liveness_probe.enabled` is `true`:

1. Runs `gog --account <gog_account> calendar list -j --max 1` — a
   minimal live Google Calendar API call. The call either succeeds
   (token alive) or returns a typed OAuth error.
2. Classifies the result:

   | Outcome | Classification | What the probe does |
   |---|---|---|
   | `rc=0` (alive) | — | Returns `None`; no issue filed. |
   | `rc≠0` + stderr contains `invalid_grant` | `dead-routine-7day` *or* `dead-unexpected` (see below) | Files a GitHub issue tagged `P1-bug`, `area/infrastructure`. |
   | Subprocess timeout, `gog` binary missing, other non-`invalid_grant` failure | `probe-error` | Files an issue tagged the same way; recovery command is `None`. |

3. The `dead-routine-7day` vs `dead-unexpected` distinction is the
   probe's only useful security signal — see the next section.

---

## Classification baseline (the routine vs unexpected call)

The Testing-mode OAuth refresh token has a hard 7-day lifetime from
**issuance** (i.e. from the manual re-auth event). When a `dead`
result lands, the probe compares "now" against an estimated 7-day
expiry and classifies:

- `|now − (baseline + 7d)| ≤ 24h` → **`dead-routine-7day`** — routine
  cycle; just re-auth. Low-noise alert.
- Otherwise → **`dead-unexpected`** — mid-week token death suggests
  a password change, manual revoke, or Google security review. Higher-
  signal alert that says "investigate at
  myaccount.google.com/permissions before re-auth."

### Why the baseline matters (#616)

The 7-day clock is anchored at OAuth **re-auth time**, not at last
token-refresh time. The keyring file's mtime advances every 6 hours
(each successful probe refreshes the access token and gogcli persists
it back), so `keyring_mtime + 7d` always slides forward to ~6 days in
the future and never lands in the ±24h window. Using the keyring
mtime as the baseline misclassifies *every* routine 7-day expiry as
`dead-unexpected`.

The fix (shipped 2026-06-16, commit `cab0a2af`) is the
`reauth_marker_glob` config field — see the next section.

---

## Manifest entry shape

For an OAuth credential to be probed, its
[`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
entry must declare a `liveness_probe` block:

```json
{
  "name": "gog-credentials-keyring",
  …
  "liveness_probe": {
    "enabled": true,
    "gog_account": "kentgale@gmail.com",
    "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_…",
    "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh",
    "reauth_marker_glob": "/home/claude/.config/gogcli/oauth-manual-state-*.json"
  }
}
```

| Field | Required when `enabled: true`? | Purpose |
|---|---|---|
| `enabled` | always | Set to `false` to keep the entry in the manifest but suppress probing. |
| `gog_account` | yes | Google account email. Passed to `gog --account`. |
| `keyring_file` | yes | Absolute path to the gogcli-managed keyring file. Used as the 7-day baseline **only when `reauth_marker_glob` is unset or matches no files** (fallback only — biased toward `dead-unexpected` false alarms; do not rely on it). |
| `recovery_command` | yes | Verbatim command embedded in any filed GitHub issue. For gog: `ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`. |
| `reauth_marker_glob` | no but **strongly recommended for any Testing-mode OAuth credential** | Glob pattern whose matching files are touched **only** by the manual re-auth flow (e.g. `~/.config/gogcli/oauth-manual-state-*.json`). The probe takes `max(mtime)` across matches as the 7-day baseline. Stable across the 6-hour probe refresh cycle. |

The manifest parser rejects unknown keys in the `liveness_probe` block —
see [manifest-liveness-probe-block.md](<../../kitty-specs/credential-liveness-probe-01KTP9M8/contracts/manifest-liveness-probe-block.md>) for the
validation rules.

---

## Adding a new credential to the probe

1. Confirm the credential is an OAuth bearer with a refresh-token cycle
   (i.e. expected death). Static API keys aren't a fit for liveness
   probing — they fail "expired" only on rotation.
2. Identify the gog account that owns the credential and the path to the
   keyring or canonical file.
3. Identify a re-auth marker path. If the credential is gogcli-managed,
   the `oauth-manual-state-*.json` glob works as shown above. If it's
   another OAuth stack, find a file that is touched only by the manual
   re-auth flow — NOT by routine token refreshes.
4. Add the `liveness_probe` block to the credential's manifest entry.
5. Run the probe manually (see below) and confirm the new credential
   appears in the cycle log; expect either `credential_alive` or, if
   it died, a `credential_dead` line with the correct classification.

---

## Operator response when an issue is filed

The probe files issues with the recovery command in the body. The
right operator response depends on classification:

### `credential-liveness-routine-7day: <name> (<date>)`

Routine cycle; just re-auth. The issue body includes the verbatim
recovery command. For `gog-credentials-keyring`, that's:

```bash
ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh
```

Wraps the gog two-step OAuth flow; ~3 min total including the browser
consent step. See
[google-workspace-ops.md §2.8](<./google-workspace-ops.md>) for the
underlying procedure if you need to step through it manually.

After re-auth, the next 6-hour probe will confirm liveness; close the
GitHub issue manually (auto-close is a future-work item per
`kitty-specs/credential-liveness-probe-01KTP9M8/spec.md` §Future Work).

### `credential-liveness-unexpected: <name> (<date>)`

The token died mid-cycle. Investigate before re-authing — the issue
body's link to
[myaccount.google.com/permissions](https://myaccount.google.com/permissions)
shows whether the OAuth grant was revoked manually or via a Google
security event. Common causes:

- Password change on the linked Google account.
- 6+ months of inactivity (refresh tokens are GC'd after long idle).
- Manual revocation at myaccount.google.com/permissions.
- Google security review (rare; emails the account first).

If nothing suspicious is found and the re-auth marker says "close to
the 7-day mark anyway," it's probably a borderline-cycle false alarm
caused by Google's clock vs office2's clock. After investigation,
re-auth via the same recovery command.

### `credential-liveness-error: <name> (<date>)`

Subprocess timeout, `gog` binary missing, or the underlying API
returned an error that isn't `invalid_grant`. The body carries the
probe's stderr excerpt; usually a one-shot transient (DNS, network)
that the next 6-hour tick resolves on its own. If it persists, check
the binary path (`GOG_BINARY` in `liveness.py`) and run a manual probe.

---

## Forcing a probe manually

The systemd service is a oneshot; trigger it ad-hoc with:

```bash
ssh office2-claude 'systemctl --user start credential-liveness-probe.service'
ssh office2-claude 'journalctl --user -u credential-liveness-probe.service --since "1 minute ago" --no-pager'
```

Or, when you want to capture per-credential output without going
through systemd:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && set -a && \
  . /data/services/openclaw/secrets/openclaw-gateway.env && set +a && \
  /usr/bin/python3 -m scripts.security.credential_health_check \
    --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json \
    --liveness-only'
```

The `/data/services/openclaw/secrets/openclaw-gateway.env` `set -a`
load is required because the probe needs `GOG_KEYRING_PASSWORD` to
decrypt the keyring; without it, you'll see
`no TTY available for keyring file backend password prompt; set GOG_KEYRING_PASSWORD`
instead of the actual token state.

---

## Troubleshooting

### Probe reports `dead-unexpected` but the actual gog call (with env loaded) returns `invalid_grant` near the 7-day mark

This is the #616 baseline-misclassification class. Check the manifest
entry's `liveness_probe.reauth_marker_glob`: if unset, the probe is
falling back to the keyring-mtime baseline (always biased toward
unexpected). Set the field per the [Manifest entry shape](<#manifest-entry-shape>)
section and re-run the probe; the next failure should classify
correctly. (Fixed in commit `cab0a2af` for `gog-credentials-keyring`.)

### Probe reports `probe-error` with `no TTY available for keyring file backend password prompt`

The probe ran without `GOG_KEYRING_PASSWORD`. Check that the systemd
service unit's `EnvironmentFile=/data/services/openclaw/secrets/openclaw-gateway.env`
line is present and the env file contains `GOG_KEYRING_PASSWORD=`. The
manual-probe command in this runbook explicitly sources that file —
copy-paste it as-is.

### Probe reports `probe-error: gog binary not found`

The `gog` binary lives at `/home/linuxbrew/.linuxbrew/bin/gog` (Linuxbrew
install). If the install path moves, `GOG_BINARY` in
`scripts/security/credential_health_check/liveness.py` must be
updated in lockstep.

### Probe never runs even though the timer is enabled

Confirm the timer is active:

```bash
ssh office2-claude 'systemctl --user status credential-liveness-probe.timer'
ssh office2-claude 'systemctl --user list-timers credential-liveness-probe.timer'
```

If the timer is enabled but `Next` is `n/a`, the
`OnCalendar=*-*-* 00,06,12,18:00:00` schedule may have been overridden
by a drop-in; check `~/.config/systemd/user/credential-liveness-probe.timer.d/`
for any override files.

---

## Related documents

- [Security Baseline Operations](<./security-baseline-ops.md>) — the sister sweep (daily 3 AM)
- [Google Workspace Operations](<./google-workspace-ops.md>) — `gog` setup, OAuth flow, manual re-auth procedure (§2.8) wrapped by `gog-reauth.sh`
- [Credential Manifest (JSON)](<../design/architecture/data/credential-manifest.json>) — authoritative list of credentials and their liveness blocks
- [Credentials & Secrets](<../design/architecture/credentials-and-secrets.md>) — narrative overview of the credential model
- [Credential Rotation Operations](<./credential-rotation-ops.md>) — operator runbook for manual rotation of each credential
- Spec: [`kitty-specs/credential-liveness-probe-01KTP9M8/`](<../../kitty-specs/credential-liveness-probe-01KTP9M8/>) — contracts, data model, and design rationale

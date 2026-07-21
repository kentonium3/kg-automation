---
title: Credential Liveness Probe Operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-06-16
last_validated: 2026-07-21
last_updated: '2026-07-21'
version: v2.0
owners: [kgale]
---

# Credential Liveness Probe Operations

The `credential-liveness-probe` is one of two periodic configuration-integrity
sweeps on office2. Every 6 hours it runs each credential's declared **probe
command** and classifies the result by exit code; when a credential dies, it
auto-files a GitHub issue with the recovery command in the body. The sister
sweep is the daily [Security Baseline Audit](<./security-baseline-ops.md>) at
3 AM, which detects unexpected drift in the system's configuration surface.

The probe is **generic** (as of #845): it is credential-agnostic. Any credential
— a Google OAuth token, a Vikunja API token, a GitHub PAT — opts in by declaring
a `command` to run plus the `dead_exit_codes` that mean "this credential is
dead". The runner runs the command and interprets the exit code; it holds no
per-credential-type logic. This replaced the original gog-specific probe (#572),
whose only subject was removed when gog was decommissioned (#819/#629), which
had orphaned the canary (perpetual `unknown`, paging every 6h — #845).

This runbook is the canonical surface for the probe. Service-specific
runbooks (e.g. [calendar-helper-ops](<./calendar-helper-ops.md>)) link here
for the probe's behavior and only document service-specific recovery details.

Tracking issues: original implementation #572; generic re-point #845.

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
06:00, 12:00, 18:00. Each probe completes in well under a second (the per-block
`timeout_seconds` bound defaults to 20 s; a real network round-trip is
~500–900 ms).

---

## What the probe does, per credential

For each manifest entry whose `liveness_probe.enabled` is `true`:

1. Runs the block's `command` (an argv list, executed with `shell=False`)
   with a `timeout_seconds` bound. The command is expected to make a cheap
   authenticated call and exit with a meaningful code — e.g. the Google
   calendar credential runs `calendar_helper --self-check`, which
   authenticates and issues a bounded `events.list(primary, max=1)`.
2. Classifies by **exit code**:

   | Outcome | Classification | What the probe does |
   |---|---|---|
   | exit `0` | alive | Logs `credential_alive`; returns `None`; no issue filed. |
   | exit ∈ `dead_exit_codes` | `dead` | Logs `credential_dead`; files a GitHub issue titled `credential-liveness-dead: <name>` with the block's `recovery_command` in the body. |
   | any other non-zero exit, timeout, or a failure to execute the command | `probe-error` | Logs `credential_probe_error`; files an issue; recovery command is `None`. |

Only an exit code the credential explicitly lists in `dead_exit_codes` is a
death. Every other non-zero outcome is a probe-error — so an environment fault
(broken venv, missing dependency, transient network error) never masquerades as
a dead credential. (This is why `calendar_helper` maps a missing-google-libs
fault to exit 1, not its auth-dead exit 3 — #845 HIGH-2.)

---

## Canary heartbeat — why the probe can't silently go `unknown`

The `credential-liveness-probe` canary (in `service-inventory.json`) greps this
service's journal over a 7h window for
`credential_alive|credential_dead|credential_probe_error|credential_liveness_cycle_complete`.
The last token is a **heartbeat** (#845): the runner emits
`credential_liveness_cycle_complete` on **every** completed cycle, even when zero
credentials have an enabled `liveness_probe`. So a running service always leaves
a marker and the canary can never fall back to `unknown` just because probes were
removed (the exact failure #819 caused). If the canary *does* read `unknown`, the
service genuinely failed to run (systemd failure, or an unreadable manifest that
aborts the cycle before the heartbeat) — a real "the check is broken" signal, not
a false alarm.

---

## Manifest entry shape

For a credential to be probed, its
[`credential-manifest.json`](<../design/architecture/data/credential-manifest.json>)
entry must declare a `liveness_probe` block. Example — the Google personal
calendar credential (the first re-pointed subject, #845):

```json
{
  "name": "felix-google-personal-calendar",
  …
  "liveness_probe": {
    "enabled": true,
    "command": ["/data/services/openclaw/felix-calendar/venv/bin/python", "-m", "scripts.google.calendar_helper", "--self-check", "--account", "personal"],
    "dead_exit_codes": [3],
    "recovery_command": "Re-mint the token on the Mac and re-stage token.json to office2 (0600). See docs/runbooks/calendar-helper-ops.md.",
    "timeout_seconds": 20
  }
}
```

| Field | Required when `enabled: true`? | Purpose |
|---|---|---|
| `enabled` | always | Set to `false` to keep the entry in the manifest but suppress probing. |
| `command` | yes | argv list to run (`shell=False`). `command[0]` MUST be an absolute path (probes run in a systemd context with a minimal PATH — for a venv-backed helper, point at the venv's `bin/python`). |
| `dead_exit_codes` | yes | Non-empty list of integer exit codes that mean the credential is dead / needs re-auth. Everything else non-zero is a probe-error. |
| `recovery_command` | yes | Verbatim recovery guidance embedded in any filed GitHub issue. |
| `timeout_seconds` | no (default 20) | Positive integer; the probe subprocess is killed and reported `probe-error` if it exceeds this. |

The manifest parser rejects unknown keys and type-invalid values (non-bool
`enabled`, non-absolute `command[0]`, non-int/`bool` `dead_exit_codes`, etc.) as
`ManifestQualityError`.

---

## Adding a new credential to the probe

The probe is generic, so adding a credential is usually a **manifest-only**
change — no code change to the runner:

1. Identify (or author) a cheap, non-interactive probe command that
   authenticates the credential and exits with a distinct, documented code on a
   genuine auth failure (distinct from environment/setup failures). Examples:
   - **Google OAuth (calendar)** — `calendar_helper --self-check` (exit 0 ok,
     3 = auth-dead). Ready today.
   - **Vikunja token** — a `curl -fsS` to a cheap authenticated endpoint (e.g.
     `/api/v1/user`); curl exits 22 on an HTTP 4xx, so `dead_exit_codes: [22]`.
   - **GitHub PAT** — `gh api user` (or a `curl` to `api.github.com`); pick the
     exit code the tool returns on a 401.
2. Ensure `command[0]` is an absolute path and, for a venv-backed probe, points
   at the venv python so its dependencies resolve in the systemd context.
3. Add the `liveness_probe` block to the credential's manifest entry.
4. Run the probe manually (see below) and confirm the credential appears in the
   cycle log with `credential_alive` (or `credential_dead` / `credential_probe_error`
   as appropriate).

---

## Operator response when an issue is filed

The probe files issues with the recovery command in the body. The
right operator response depends on classification:

### `credential-liveness-dead: <name> (<date>)`

The refresh token is no longer valid. Because the gog OAuth app is
published (#731), this is never a routine expiry — investigate before
re-authing. The issue body links to
[myaccount.google.com/permissions](https://myaccount.google.com/permissions),
which shows whether the OAuth grant was revoked manually or via a Google
security event. Common causes:

- Password change on the linked Google account.
- 6+ months of inactivity (refresh tokens are GC'd after long idle).
- Manual revocation at myaccount.google.com/permissions.
- Google security review (rare; emails the account first).

After investigating, recover via the verbatim `recovery_command` in the issue
body (each credential declares its own). For `felix-google-personal-calendar`,
that means re-minting the token on the Mac and re-staging `token.json` to office2
— see [calendar-helper-ops.md](<./calendar-helper-ops.md>). After recovery, the
next 6-hour probe confirms liveness; close the GitHub issue manually (auto-close
is a future-work item per
`kitty-specs/credential-liveness-probe-01KTP9M8/spec.md` §Future Work).

### `credential-liveness-error: <name> (<date>)`

The probe subprocess timed out, could not be executed (missing interpreter/
binary), or exited non-zero with a code that is NOT in the credential's
`dead_exit_codes` (an environment or transient fault, deliberately distinct from
a real death). The body carries the probe's stderr excerpt. Usually a one-shot
transient (DNS, network) that the next tick resolves. If it persists, run the
probe command manually and check the probe's own health — for the calendar
credential, confirm the venv exists and `calendar_helper --self-check` runs
under it.

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
ssh office2-claude 'cd /home/claude/kg-automation && /usr/bin/python3 -m scripts.security.credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json --liveness-only'
```

You can also run a credential's probe command directly to see its raw exit code
— e.g. the calendar self-check under its venv:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper --self-check --account personal; echo "exit=$?"'
```

---

## Troubleshooting

### The canary reports `credential-liveness-probe: unknown`

Since #845 a running service always emits the `credential_liveness_cycle_complete`
heartbeat, so `unknown` means the **service did not complete a cycle** — not that
a probe was missing. Check that the timer fired and the service didn't crash:

```bash
ssh office2-claude 'systemctl --user status credential-liveness-probe.service --no-pager'
ssh office2-claude 'journalctl --user -u credential-liveness-probe.service --since "7 hours ago" --no-pager | tail'
```

A `ManifestUnreadableError` (bad JSON / missing manifest) aborts the cycle before
the heartbeat and is the most likely cause of a genuine `unknown`.

### Probe reports `probe-error` for a Google credential

The `calendar_helper --self-check` exited non-zero with a code other than its
auth-dead 3 (e.g. 1 = operational: the venv is broken or a dependency is
missing). Run the direct probe command above to see the stderr; confirm the venv
at `/data/services/openclaw/felix-calendar/venv` exists and is provisioned (see
[calendar-helper-ops.md](<./calendar-helper-ops.md>)). A broken venv is an
environment fault, deliberately NOT reported as a dead credential.

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

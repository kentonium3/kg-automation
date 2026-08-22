---
title: Security Baseline Operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-27
last_validated: 2026-05-27
last_updated: '2026-08-22'
version: v1.0
owners: [kgale]
---

# Security Baseline Operations

The daily security audit at 3 AM on office2 compares the live system
against a set of baselines and emits an alert when anything drifts.
After any intentional change to the audited surface — a new service,
an updated container image, a new cron entry, a config edit picked up
by one of the checks — the baselines must be regenerated so subsequent
runs don't alert on the now-expected state.

This runbook is the canonical procedure. Service-specific runbooks
(vikunja-ops, openclaw-ops, etc.) link here and only document
**when** their service needs a reset, not how.

## Locations

- **Audit script**: `/data/services/security-monitor/scripts/audit.sh`
- **Baselines**: `/data/services/security-monitor/baselines/`
- **Logs**: `/data/services/security-monitor/logs/audit-YYYY-MM-DD.log`
- **Alerts**: `/data/services/security-monitor/logs/alerts-YYYY-MM-DD.log`
- **Drift events** (consumed by doc-audit): `/data/services/security-monitor/logs/drift-events.jsonl`

## What the audit checks

| Check | Baseline file |
|---|---|
| Python `.pth` startup-hijack files | `pth-files.txt` |
| System pip package list | `pip-packages.txt` |
| Homebrew packages + taps | `brew-packages.txt`, `brew-taps.txt` |
| Docker images | `docker-images.txt` |
| Listening ports | `listening-ports.txt` |
| Enabled systemd services (system + user) | `enabled-services.txt`, `systemd-user-units.txt`, `systemd-user-dropins.txt` |
| Systemd user unit-file **contents** (functional, normalized — #818) | `systemd-user-unit-contents.txt` |
| SSH `authorized_keys` | `ssh-keys.txt` |
| `/etc/hosts` (hash) | `hosts-hash.txt` |
| Crontabs | `crontabs.txt` |
| OpenClaw cron + config | `openclaw-cron.txt`, `openclaw-config.txt` |

> **Names vs contents (#818).** `systemd-user-units.txt` tracks enabled unit
> *names* and `systemd-user-dropins.txt` the file *inventory* (paths + type), but
> neither hashes a unit file's *contents* — so a change to `ExecStart` /
> `Environment` *inside* an existing enabled unit (a stale or tampered body, the
> #816 class) was invisible. `systemd-user-unit-contents.txt` closes that gap by
> baselining each unit file's functional content (comments + blank lines +
> trailing whitespace normalized out, mirroring the #817 unit-drift canon), so a
> directive change trips the daily audit. It **auto-creates** on the first run
> after deploy — no manual reset — and complements the #817 deployed-vs-repo
> canary (that compares to the repo; this compares to the last approved baseline,
> so it also covers tamper and non-repo-managed units).

## Automatic rebaseline (felix-deployer)

As of mission #618, felix-deployer automatically rebaselines the
security-monitor baselines when it applies a change that touches an
audited surface. **No operator action is needed on the happy path.**

### How it works (deferred-confirm flow)

1. On each `git pull`, felix-deployer intersects the pulled commit range
   against the audited-surface registry
   (`docs/design/architecture/data/audited-surfaces.json`). If any
   audited path changed, it writes a **rebaseline-pending token** at
   `/data/services/felix-deployer/state/rebaseline-pending.json`
   recording the matched surface IDs, expected affected baselines, and
   `pending_since` timestamp.

   **CLI-mutation deploys.** Some deploys drift a baseline without any
   tracked-file change — e.g. an `openclaw cron rm` that drifts
   `openclaw-cron.txt` but touches no `openclaw.json`. These have no
   repo-file signal for the observe step, so the deploy manifest declares
   the baselines it will drift via an `expected_baselines` field
   (requires `audited_surface: true`; each name must be a known baseline).
   Those declared baselines are folded into the pending token's expected
   set, so the auto-rebaseline covers them and **no manual reset is
   needed**. See the felix-deployer reference in
   [deployment.md](<./deployment.md#manifest-expected_baselines-declaration>).

2. On each subsequent tick while a pending token exists, the deployer
   runs a **read-only** audit (baselines present — compare mode, no
   reset) to check whether expected drift has appeared yet:

   - **Drift confined to the expected baselines** — the surface has
     deployed and its fingerprint has changed. The deployer rebaselines
     (`rm baselines/* && sg docker -c audit.sh`), verifies that the
     baseline count equals `expected_baseline_count` from the registry
     and that the audit reports clear, records the `completed` outcome on
     the tick log (`rebaseline_reconcile` / `rebaseline_stamped`) and on the
     applied record's `rebaseline:` field (#688), and clears the token.

   - **Audit clean (no drift)** — the committed change did not alter
     the hashed content of any monitored surface (e.g. a comment-only
     edit to an audited path, or the surface already matched the
     baseline). Token is cleared with `rebaseline: not_required`.

   - **Drift extends beyond the expected baselines** — potential
     security event. The deployer does NOT auto-rebaseline; it emits an
     ntfy alert (`rebaseline_unexpected_drift`) and leaves the baselines
     intact for human review.

3. If the pending token ages past the configured max age and no drift is
   ever confirmed, the deployer emits an ntfy alert
   (`rebaseline_stale`) so a human can investigate why the surface never
   appeared to deploy.

### Observability outcomes

The outcome is recorded in two places (#688): the real-time felix-deployer tick
log (`/data/services/felix-deployer/logs/<date>.jsonl`, `rebaseline_reconcile` /
`rebaseline_stamped` events correlated to the applied manifest name) AND, as the
durable per-deploy annotation, a `rebaseline:` field stamped onto the
`deploys/applied/<NNNN>-<name>.yaml` entry after reconcile (`outcome` + `at_utc`
+ details), in a follow-up `deploy(rebaseline): …` commit. Note: the field holds
the outcome as of the applying tick — a deploy whose drift lands in the grace
window is stamped `pending_clean` and is not re-stamped by the later tick that
resolves it (same-tick MVP; the tick log carries the terminal outcome).

| Outcome | Meaning |
|---|---|
| `not_required` | No audited surface in the pulled commit range. |
| `pending_set` | Audited surface observed; pending token written; awaiting drift confirmation. |
| `completed` | Expected drift confirmed; baselines regenerated and verified healthy. |
| `cleared_clean` | Pending token cleared because the audit was clean (no drift to confirm). |
| `unexpected_drift` | Drift beyond the expected set; operator alert emitted; baselines left intact. |
| `failed` | Rebaseline attempted but verification failed (count mismatch or audit not clear); operator alert emitted; applied code left in place. |
| `stale` | Pending token exceeded max age without drift confirmation; operator alert emitted. |

### ntfy alerts

felix-deployer emits exactly one ntfy alert per event:

| Topic suffix | Trigger |
|---|---|
| `rebaseline_failed` | Regeneration failed or baseline-count mismatch after a rebaseline attempt. |
| `rebaseline_unexpected_drift` | Observed drift extends beyond the expected baseline set. |
| `rebaseline_stale` | Pending token aged out without drift confirmation. |

### When a human is still involved

- **Out-of-band changes** — a change made directly on office2, bypassing
  felix-deployer, is invisible to the automatic flow. The daily security
  audit surfaces it as drift. Investigate, then reset manually (see the
  manual procedure below).

- **Unexpected drift** — if the `unexpected_drift` alert fires, do not
  auto-reset. Inspect the alert and the audit log to determine whether
  the drift is a security event or a misconfiguration before deciding
  whether to reset.

- **Rebaseline failed** — if the `rebaseline_failed` alert fires, the
  applied code is in place and working, but the baseline reset failed.
  Investigate and reset manually once the root cause is clear.

## Manual reset procedure (fallback)

Use this for out-of-band changes, after a `rebaseline_failed` alert,
or whenever the automatic flow cannot run. Run as the `claude` user on
office2 via `ssh office2-claude`. The `sg docker -c` wrapper supplies
the docker group needed for the image diff.

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

Expected output on success: `Security audit YYYY-MM-DD: All clear` and
14 baseline files freshly written in `baselines/`.

## Verifying the reset

```bash
ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
ssh office2-claude 'tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
```

Expect 14 files and an `AUDIT COMPLETE: All clear` line stamped near
the time of the reset.

## When to reset

The audit is the authority on "the system changed unexpectedly." On the
happy path (changes via felix-deployer), the reset is automatic. For
out-of-band changes or post-alert recovery, reset manually after any
**intentional** change to one of the audited surfaces. Service runbooks
list specific triggers:

- Vikunja deploy / image upgrade → [vikunja-ops.md](<./vikunja-ops.md#security-baseline-trigger>)
- OpenClaw deploy / config change → [openclaw-ops.md](<./openclaw-ops.md#security-baseline-trigger>)
- New service added per [deployment.md](<./deployment.md>)
- Bulk repo changes that touch `openclaw-config.txt` content (e.g.,
  agent-config sweeps)
- **Deploy-pipeline primitives** — changes to `scripts/deploy/lib/**` (and
  `deploys/{queued,applied,failed}/*.yaml`) are the `deploy-pipeline` audited
  surface. When such a change ships via a **controlled operator bootstrap**
  rather than the felix-deployer manifest tick, the rebaseline is a **manual**
  out-of-band reset — not the auto-rebaseline happy path. Worked example: the
  #667 prompt-sync FETCH_HEAD-race bootstrap
  (`deploys/applied/0012-prompt-sync-ff-race.yaml`, mission
  prompt-sync-ff-race-01KX3SZC) added
  `scripts/deploy/lib/{gitsync,deploylock,health}.py`. **Confirm the observed
  drift is expected-only first** (only those new-file surfaces should differ);
  if drift extends beyond the change, investigate before resetting. Then run the
  manual reset below. See the controlled-bootstrap deploy pattern in
  [deployment.md](<./deployment.md>). Note the actor edits to
  `_tick.py` / `deploy_agent_prompts.py` / `notify.py` are **not** registry-matched
  and do not by themselves trigger a rebaseline.

- **`qa-register` rebuilds (interim, kentonium3/kg-automation#886)** — the
  spec-kitty-qa QA Pipeline DB component runs on office2 out-of-band (no
  `deploys/queued` manifest), so felix-deployer's expected-drift token never
  suppresses its drift. Its image tag rolls on **every rebuild**
  (`9bacc37` → `cc3220f` → `fb679e6` in two weeks), and each roll re-drifts
  `docker-images.txt`, restarting the daily 03:00 alert until reset. **Expected
  drift is `docker-images.txt` only, naming `qa-register:*`.** If drift extends
  beyond that, investigate before resetting. This is a knowingly-accepted manual
  step (option (d) on #886): automating it — either tag normalisation in
  `audit.sh` or bringing qa-register under the manifest pipeline — was judged
  disproportionate for a component scheduled to leave the host per #887. **When
  #887 lands, delete this bullet.**

If you see drift alerts and aren't sure whether the change is
intentional, inspect `logs/alerts-YYYY-MM-DD.log` for the diff before
resetting.

## Integration verification (post-merge canary)

This section documents the explicit integration verification for mission
#618. A pre-merge live smoke is impossible because the auto-rebaseline
code goes live on office2 only on the felix-deployer tick *after* the
mission merges. The verification is an **operator-run post-merge canary**
against the real office2 service state. Its outcome is the mission's
**merge acceptance criterion**: the merge commit (or its closing-issue
comment) must record the canary result alongside the Rebaseline note.

### SC-001 / SC-003 — happy path and not-required path

**After the next real audited-surface deploy via felix-deployer:**

1. Inspect the tick log for the deploy that landed the audited-surface
   change:
   ```bash
   ssh office2-claude 'tail -50 /data/services/felix-deployer/logs/$(date +%Y-%m-%d).jsonl'
   ```
2. Confirm the tick sequence shows `pending_set` followed (on a later
   tick) by `completed`.
3. Confirm baselines are healthy:
   ```bash
   ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
   ```
   Expect the count to equal `expected_baseline_count` from
   `docs/design/architecture/data/audited-surfaces.json` (currently 14).
4. Confirm no operator action was needed (no manual reset command was
   run).

**For a deploy that touches no audited surface:**

1. Check the tick log entry for the manifest.
2. Confirm outcome is `not_required` (no pending token written, no reset
   attempted).

### SC-002 — next scheduled audit clean

After the auto-rebaseline completed (SC-001), wait for the next 3 AM
daily security audit and confirm:

```bash
ssh office2-claude 'tail -10 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
```

Expect `AUDIT COMPLETE: All clear` with no drift attributed to the
intentional change. Zero false-positive drift alerts.

### SC-004 — simulated failure path

To exercise the failure path without a real failure, the operator can:

1. Temporarily set an incorrect `expected_baseline_count` in a test
   copy of `audited-surfaces.json`, or arrange for the audit to return
   non-zero after a rebaseline (e.g. temporarily corrupt one baseline
   file).
2. Trigger a rebaseline by landing an audited-surface change.
3. Observe the tick log for `failed` outcome.
4. Confirm exactly one ntfy alert with topic `rebaseline_failed` was
   emitted.
5. Confirm the `failed` outcome is recorded both on the tick log (the
   `rebaseline_reconcile` / `rebaseline_stamped` events in
   `/data/services/felix-deployer/logs/<date>.jsonl`, correlated to the applied
   manifest name) and as the `rebaseline:` field on the applied YAML record
   (`deploys/applied/<NNNN>-<name>.yaml`, with `outcome: failed` + `error_summary`).
6. Confirm the applied code is still in place (no rollback).
7. Restore the correct `expected_baseline_count` and reset manually.

Alternatively, inspect the unit tests in `tests/deploy/test_rebaseline.py`
which cover all failure branches with mocked audit and notification
dispatch — the SC-004 live canary is the confirmation that the mocked
behavior matches real office2.

## Interaction with doc-audit (drift-events.jsonl)

The audit writes to the same `drift-events.jsonl` that the doc-audit
driver reads. A baseline reset itself does **not** emit drift events
(the audit sees no prior baseline to diff against). New drift events
only fire on subsequent real changes.

## Secrets provisioning (agent rule + standing test key)

Two conventions keep API keys out of shell history and keep production out of testing.

**1. NEVER provision a secret with `echo` or an inline literal — this is an agent rule.**
Any command that puts a secret *value on the command line* — `echo 'sk-…' > file`, `export KEY=sk-…`,
etc. — writes the secret into `~/.bash_history` in cleartext. An earlier session's
`echo 'sk-ant-…' > .../secrets/anthropic` did exactly this and exposed the OpenClaw **production**
Anthropic key (found + scrubbed 2026-07-22; the key still had to be rotated — scrubbing history does
not revoke it). **An agent must never hand a user an `echo`/inline-literal command for a secret — and a here-string
(`cmd <<< 'sk-…'`) is NOT a safe substitute.** Bash records the *entire command line*, including the
here-string, into `~/.bash_history` exactly like `echo` does. (An earlier version of this runbook wrongly
recommended `install /dev/stdin <<< '…'`; corrected 2026-07-22 after it was shown to expose the value.)
The only safe method keeps the value **off the command line entirely** — capture an interactive paste
into a variable with `read -rs`, then write it:

```bash
# The recorded command line holds only $SECRET, never the value. Paste at the silent prompt, press Enter.
read -rs SECRET
printf '%s\n' "$SECRET" | sudo -u claude tee /path/to/secret-file >/dev/null   # sudo prompts on the tty
unset SECRET
```

**Do not** use a bare interactive `tee`/`install /dev/stdin` (paste-then-Ctrl-D): those truncate the
file on open, so if the paste doesn't register before EOF the file is silently zeroed (this happened
2026-07-22 and briefly emptied the OpenClaw key file). Capturing with `read -rs` first sidesteps that
race. After any secret handling, verify no stray reference remains: `grep -c 'sk-ant' ~/.bash_history`.

**2. Use a dedicated test/dev key — never the production key — for spikes and tests.**
Testing runs against a separate Anthropic **Workspace** (its own key + a spend cap) so billing, rate
limits, and rotation are isolated from production; if a test key leaks it rotates with zero prod impact.
The standing test key lives at **`~/.config/felix/anthropic-test.env`** on office2 (claude user, `0600`).
Spikes source it (`set -a; . ~/.config/felix/anthropic-test.env; set +a`) instead of provisioning a key
ad-hoc each run. Related: kg-automation #850 (throwaway-sandbox carve-out).

## Related documents

- [office2 Backup and Security Model](<../design/office2-backup-and-security.md>) — overall security posture and audit context
- [Security Posture (architecture)](<../design/architecture/security-posture.md>) — change-control tiers + audit surface table
- [Deployment Runbook](<./deployment.md>) — when a feature deploy should trigger a reset

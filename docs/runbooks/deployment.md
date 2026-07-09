---
title: Deployment Runbook
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-06-12'
---

# Deployment Runbook

**This page has moved.** The canonical deploy discipline is now documented
at [`docs/runbooks/deploy/discipline.md`](<./deploy/discipline.md>). All
conceptual questions about how a deploy reaches office2 — manifest shape,
applier behavior, tier policy, failure handling, rebaseline obligation —
are answered there.

This page is preserved for two reasons:

1. **Grandfathered scripts at `scripts/deploy/deploy-*.sh` are still in use.**
   The 7 pre-discipline deploy scripts continue to work without change; sibling
   issue #548 handles their cleanup. Structural information about those
   scripts is preserved below for the operators and agents that still touch
   them.
2. **Stable URL for inbound links.** Older docs, ADRs, GitHub issues, and
   external bookmarks link here. Rather than break those links, this page
   redirects to the canonical discipline runbook.

For **any new deploy after the pull-based-deploy-pipeline mission merges**,
read [`docs/runbooks/deploy/discipline.md`](<./deploy/discipline.md>). Do not
author new deploys against the patterns below.

---

## Grandfathered scripts (read-only reference)

The following scripts in `scripts/deploy/` were authored before the
manifest discipline landed. They continue to work — re-run them as needed
for their original purpose — but they should not be used as templates for
new work.

| Script | Purpose |
|---|---|
| `scripts/deploy/deploy-f013.sh` | Reference legacy script (pre-discipline canonical example) |
| `scripts/deploy/deploy-f014.sh` | Legacy feature deploy |
| `scripts/deploy/deploy-f026.sh` | Legacy feature deploy |
| `scripts/deploy/deploy-028.sh` | Legacy mission-numbered deploy |
| `scripts/deploy/deploy-149.sh` | Legacy mission-numbered deploy |
| `scripts/deploy/deploy-felix-admin-calendar.sh` | Legacy slug-named deploy |
| `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh` | Legacy slug-named deploy |

These scripts follow the legacy pattern: a single self-contained bash
script invoked from the Mac with strict-order-of-operations safe-deploy
steps, no shared library, no manifest. Issue #548 will migrate them or
retire them — until then they remain authoritative for their original
purpose.

### Legacy structural notes (preserved for the grandfathered scripts)

The legacy scripts assume the same prerequisites the new discipline does:

- `ssh office2-claude` works (Tailscale connected, SSH host alias in
  `~/.ssh/config`).
- The script is run from a clean `main` checkout.
- The relevant risk tier has been classified per
  `docs/design/architecture/data/change-risk-taxonomy.json`.

The legacy scripts target the same office2 paths used by the manifest
discipline:

- Agent workspaces: `/data/services/openclaw/{agent-slug}/`
- Skills: `/home/claude/.openclaw/skills/{skill-slug}/`
- Python utilities: per-feature paths under `/home/claude/.openclaw/` or
  `/data/services/`.
- Cron jobs: registered via `ssh office2-claude 'openclaw cron add ...'`,
  never via system crontab.
- Systemd timers: unit files installed under
  `~/.config/systemd/user/` and enabled with
  `systemctl --user enable --now <unit>.timer`.

---

## After deployment (still applies)

These post-deploy obligations are unchanged by the new discipline:

### Architecture documentation updates

Features that deploy new services, agents, or scheduled jobs must update
`docs/design/architecture/data/service-inventory.json` and the
corresponding Markdown view as part of the same mission merge. This is the
documentation-sync standing requirement; it is not optional.

### Security baseline reset (FR-018 rebaseline obligation)

After deploying new services or modifying existing audited surfaces, reset
the security audit baselines on office2. See
[`docs/runbooks/security-baseline-ops.md`](<./security-baseline-ops.md>) for
the canonical procedure. The rebaseline obligation applies regardless of
whether the deploy goes through the manifest discipline or a grandfathered
script.

---

## felix-deployer rebaseline behavior (reference)

On the happy path, felix-deployer resets the security-monitor baselines
automatically after a pipeline deploy that touches an audited surface, so
the operator is not the load-bearing component (see the "Rebaseline
obligation" section in `CLAUDE.md` and the deferred-confirm flow in
[`security-baseline-ops.md`](<./security-baseline-ops.md#automatic-rebaseline-felix-deployer>)).
Three behaviors of that flow are load-bearing for anyone authoring or
debugging a deploy:

### Watermark-based observe range

felix-deployer decides which commits to scan for audited-surface changes
using a **persisted last-observed-head watermark** rather than the range of
its own `git pull`. The watermark is stored at:

```
/data/services/felix-deployer/state/rebaseline-observed-head.json
```

Each tick the observe range is `last_observed_head..post_pull_head`, where
`last_observed_head` is read from the watermark file and `post_pull_head` is
the checkout HEAD after the tick's `git pull --ff-only`. Because the range
starts from the watermark — not from the tick's own pull — the deployer
detects audited-surface changes even when an **out-of-band** `git pull`
fast-forwarded the checkout before the tick ran (the #685 defect). After
observe and reconcile complete, the deployer advances the watermark to the
end-of-tick HEAD (including its own `deploy(applied)` bookkeeping commit),
so it never re-observes commits it made itself. On the first tick after this
code ships — when the watermark file does not yet exist — the deployer falls
back to the tick's own pre-pull HEAD as the range base (legacy behavior) and
writes the watermark for subsequent ticks.

### Manifest `expected_baselines` declaration

The observe range only sees drift that has a **repo-file signal**. A deploy
that mutates state via a runtime CLI with no tracked-file change — e.g. an
`openclaw cron rm` that drifts `openclaw-cron.txt` without touching any
`openclaw.json` — produces no matched audited surface, so reconcile would
classify the resulting drift as `unexpected_drift`.

For those CLI-mutation deploys, the manifest declares the baselines it will
drift via an optional `expected_baselines` field:

```yaml
audited_surface: true
expected_baselines:
  - openclaw-cron.txt
```

When such a manifest is applied in a tick, its declared baselines are unioned
into the pending rebaseline token's `expected_baselines`, so reconcile sees
the drift as **expected** (D ⊆ E) and rebaselines to `completed` instead of
alerting. Validation rules (enforced by `scripts/deploy/lib/manifest.py`):

- Each declared name **must be a known security-monitor baseline** (validated
  against the audited-surfaces registry); an unrecognized name fails manifest
  validation rather than being silently ignored.
- `expected_baselines` **requires `audited_surface: true`**; declaring
  baselines on a non-audited manifest is a validation error.
- A manifest that declares **no** `expected_baselines` behaves exactly as
  before — no behavior change (backward compatible).

### Same-tick clear grace rule

A pending token whose baselines were created or folded in the current tick is
**not** cleared on an empty-drift (`D=∅`) audit in that same tick. A deploy's
audited effect can materialize shortly after apply, so clearing on the first
empty audit would delete the only memory of the pending rebaseline. Instead
reconcile returns `pending_clean` and leaves the token; the clear is deferred
until a subsequent tick (once the token has aged past the grace window,
currently ~330s / roughly one tick). Only then, on a still-clean audit, is the
token `cleared_clean`.

### Rebaseline outcome on the applied record

After reconcile, the deployer stamps the tick's rebaseline outcome onto the
applied YAML record(s) written that tick (#688) — the durable per-deploy
artefact — in addition to the real-time tick-log events:

```yaml
rebaseline:
  outcome: completed        # completed / cleared_clean / pending_clean /
                            #   not_required / unexpected_drift / inconclusive / failed
  at_utc: '2026-07-09T03:22:55Z'
  baseline_count: 14        # on completed
  # error_summary: ...      # on failed
  # unexpected: [...]        # on unexpected_drift
```

Only **audited** deploys are stamped. A `not_required` reconcile means no pending
token existed (a non-audited deploy — the common case), so the record carries **no**
`rebaseline` field; its absence means "no rebaseline was in play" and avoids a
second commit on every routine deploy.

The applied record is committed early in the queue loop (so a crash never
re-runs a non-idempotent entrypoint); the outcome is known only after reconcile,
so it is written in a **second** `deploy(rebaseline): …` commit whose SHA feeds
the watermark advance (the stamp commit is never re-observed). **Limitation
(same-tick MVP):** the field holds the outcome as of the applying tick — a deploy
whose drift lands in the grace window is stamped `pending_clean` and is not
re-stamped by the later tick that resolves it; the tick log carries the terminal
outcome. Tracked for a future enhancement.

---

## Two-actor shared-checkout lock (deploylock)

Two systemd-timed actors share the single office2 checkout at
`/home/claude/kg-automation`:

- **felix-deployer** — the manifest applier (`felix-deployer.timer`, ~5 min).
- **agent-prompt-sync** — the Felix agent-prompt sync (`agent-prompt-sync.timer`,
  ~5 min).

Both advance the checkout to `origin/main` every tick, and felix-deployer keeps
mutating the checkout after the pull (queue-apply commits, applied-record
commit/push, rebaseline stamp commits, watermark writes). Two concurrent
working-tree/index mutations on one checkout race.

**Race-immune advance.** Neither actor uses a bare `git pull` anymore. Both
fetch, then fast-forward the atomic remote-tracking **ref** `origin/main`
(`git merge --ff-only origin/main`) via `scripts/deploy/lib/gitsync.py`
(`advance_checkout`). The historical `fatal: Cannot fast-forward to multiple
branches` came from concurrent writers clobbering the single shared
`.git/FETCH_HEAD` and then merging from it; merging the per-ref-locked
`origin/main` instead removes `FETCH_HEAD` from the merge path entirely, so the
race is gone even before the lock (#667).

**Actor-level lock.** Each actor additionally wraps its **entire**
checkout-mutating critical section in a shared advisory lock,
`scripts/deploy/lib/deploylock.py` (`deploylock`, `fcntl.flock(LOCK_EX |
LOCK_NB)`), so felix-deployer's post-pull commit/push/stamp phase never overlaps
prompt-sync's fetch/merge/copy. The lock file is a neutral shared path
(`/data/services/deploy/locks/office2-checkout.lock` by default, overridable via
the `DEPLOY_CHECKOUT_LOCK` env var). Acquisition is **non-blocking with a bounded
retry (~5 s)**: if the other actor holds the lock, the tick **defers cleanly** to
its next interval (a benign `lock_unavailable` — logged, but NOT a health
failure). `flock` auto-releases if the holder dies, so a crashed actor never
wedges the other.

**The lock directory must be provisioned by the bootstrap.** `deploylock()`
`mkdir`s the lock file's parent at runtime, so if `/data/services/deploy` is not
creatable by the `claude` user the **first tick crashes BOTH actors** with a
`PermissionError`. The controlled bootstrap MUST create and verify the directory
as the `claude` user **before** restarting the timers, and it must be writable
by `claude`:

```
ssh office2-claude 'mkdir -p /data/services/deploy/locks && test -w /data/services/deploy/locks && echo lock-dir-ok'
```

**Health signal.** A per-actor watermark (`scripts/deploy/lib/health.py`) counts
only *confirmed* advance failures (`diverged | fetch_failed | merge_failed`) and
fires at most one ntfy alert per failure streak, so a silent multi-week stall
(the original #667 harm) is impossible. `lock_unavailable` defers do **not**
count.

The actor-level concurrency proof for all of the above lives in
`tests/deploy/test_actor_concurrency.py` — it runs both real tick bodies
barrier-synchronized through one lock against one checkout (seeded with a stale
extra origin branch) over 120 overlapped rounds.

## Controlled-bootstrap deploy pattern (not a queued manifest)

Some changes **cannot** ride the normal `deploys/queued/<name>.yaml` self-pull
path and must be deployed as a **controlled operator bootstrap**, recorded as a
`deploys/applied/<NNNN>-<name>.yaml` record (`apply_mode: bootstrap`) rather than
a queued manifest. Two reasons force this class:

1. **Chicken-and-egg on the deploy mechanism itself.** When the change *is* the
   git-advance path (e.g. #667 fixed the very `git pull` both actors use), the
   fixed code can only arrive via that same broken pull. Relying on the broken
   path to deliver its own fix is unsound — so the operator fast-forwards the
   checkout **by hand** with the race-immune form
   (`git fetch origin main && git merge --ff-only origin/main`) while both timers
   are stopped, then restarts them.
2. **Queued manifests are not record-only.** The manifest schema requires an
   executable `entrypoint` that felix-deployer runs `--dry-run`/`--apply`. A
   change with nothing to *run* (only a checkout fast-forward + a manual
   rebaseline) has no valid entrypoint, so it cannot be a queued manifest.

**Shape of the bootstrap record.** It is a `deploys/applied/` YAML with
`apply_mode: bootstrap`, the six required manifest fields, and (for Tier 1/2) a
`verification` block. Because there is no script, the `entrypoint` names a
manual-bootstrap path purely to satisfy the schema; the actual step-by-step
sequence lives in `notes` and in the mission quickstart. `0012-prompt-sync-ff-race.yaml`
is the worked example (#667): stop both timers → manual `--ff-only` merge →
verify the new `scripts/deploy/lib/**` files present → delete the stale origin
lane branch → **manual** audited-surface rebaseline → **provision + verify the
shared lock directory** (`mkdir -p /data/services/deploy/locks`, writable by
`claude`; see the deploylock note above) → restart both timers. If the next free
applied number is taken at deploy time, the operator renames the file before
committing (the applied sequence stays gap-free and monotonic).

**Rebaseline is manual for a bootstrap.** A controlled bootstrap is an
*out-of-band* change (not applied by felix-deployer through the manifest tick),
so its audited-surface rebaseline is a **manual** out-of-band reset — see
[`docs/runbooks/security-baseline-ops.md`](<./security-baseline-ops.md>) — not
the deployer's auto-rebaseline happy path.

---

## Troubleshooting (legacy scripts only)

For new deploys (manifest discipline), failure handling is documented in
[`docs/runbooks/deploy/discipline.md`](<./deploy/discipline.md>) under the
**Failure handling** section.

For legacy scripts:

**SSH connection refused**
- Confirm Tailscale is connected: `tailscale status`
- Confirm the claude account is reachable: `ping 100.92.197.90`

**Permission denied on office2**
- The `claude` account has scoped sudo for specific operations
- Operations requiring `kgale` permissions must be run manually by Kent

**OpenClaw cron job not appearing**
- Verify OpenClaw gateway is running:
  `ssh office2-claude "systemctl --user status openclaw-gateway"`
- Check cron registration: `ssh office2-claude "openclaw cron list"`

**Systemd timer not firing**
- Check timer status: `ssh office2-claude "systemctl --user list-timers"`
- Check service logs:
  `ssh office2-claude "journalctl --user -u {service} --since today"`

---

## Related documents

- [`docs/runbooks/deploy/discipline.md`](<./deploy/discipline.md>) — **canonical** deploy discipline
- `docs/runbooks/openclaw-ops.md` — OpenClaw service management
- `docs/runbooks/security-baseline-ops.md` — rebaseline obligation procedure
- `docs/runbooks/maintenance.md` — branch and CI conventions
- `docs/design/architecture/change-control.md` — architecture doc update protocol and risk-tiered change control
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 0/1 deployment pre-flight
- `docs/runbooks/governance/post-change-verification.md` — Tier 0/1/2 post-change verification

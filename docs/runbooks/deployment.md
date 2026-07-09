---
title: Deployment Runbook
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-06-12'
---

# Deployment Runbook

**This page has moved.** The canonical deploy discipline is now documented
at [`docs/runbooks/deploy/discipline.md`](deploy/discipline.md). All
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
read [`docs/runbooks/deploy/discipline.md`](deploy/discipline.md). Do not
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
[`docs/runbooks/security-baseline-ops.md`](security-baseline-ops.md) for
the canonical procedure. The rebaseline obligation applies regardless of
whether the deploy goes through the manifest discipline or a grandfathered
script.

---

## felix-deployer rebaseline behavior (reference)

On the happy path, felix-deployer resets the security-monitor baselines
automatically after a pipeline deploy that touches an audited surface, so
the operator is not the load-bearing component (see the "Rebaseline
obligation" section in `CLAUDE.md` and the deferred-confirm flow in
[`security-baseline-ops.md`](security-baseline-ops.md#automatic-rebaseline-felix-deployer)).
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

---

## Troubleshooting (legacy scripts only)

For new deploys (manifest discipline), failure handling is documented in
[`docs/runbooks/deploy/discipline.md`](deploy/discipline.md) under the
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

- [`docs/runbooks/deploy/discipline.md`](deploy/discipline.md) — **canonical** deploy discipline
- `docs/runbooks/openclaw-ops.md` — OpenClaw service management
- `docs/runbooks/security-baseline-ops.md` — rebaseline obligation procedure
- `docs/runbooks/maintenance.md` — branch and CI conventions
- `docs/design/architecture/change-control.md` — architecture doc update protocol and risk-tiered change control
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 0/1 deployment pre-flight
- `docs/runbooks/governance/post-change-verification.md` — Tier 0/1/2 post-change verification

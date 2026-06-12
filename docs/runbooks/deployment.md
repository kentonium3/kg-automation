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

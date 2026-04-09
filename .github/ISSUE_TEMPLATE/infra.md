---
name: Infra
about: Infrastructure change — server, networking, credentials, hardware, config
title: "Infra: "
labels: P3-candidate, spec: brief
assignees: ''
---

<!--
TWO-STAGE SPEC LIFECYCLE:
  1. "spec: brief" (default) — capture the idea. Fill in what you know.
  2. "spec: ready" — before entering spec-kitty workflow, all template
     sections must be complete. Swap the label when ready.

Infrastructure changes are governed by the five-tier risk taxonomy.
Identify the tier FIRST — it determines what Claude Code can and cannot do.
See docs/design/architecture/data/change-risk-taxonomy.json
-->

## Summary

<!--
What is changing and why.
-->

---

## Risk tier

<!--
Select one. If uncertain, default to the higher tier.
-->

- [ ] **Tier 0 — Hard Lock** (UFW, iptables, sshd_config, sudoers, system chmod/chown)
  *Claude Code generates script only. Kent executes manually.*
- [ ] **Tier 1 — Verification Required** (Tailscale, Docker networks, port bindings, proxy)
  *Connectivity confirmed before and after. Pre-flight checklist required.*
- [ ] **Tier 2 — Snapshot Required** (DB schemas, service env files, Docker Compose, app config)
  *Restic backup confirmed before modifying.*
- [ ] **Tier 3 — Standard** (Python scripts, agent prompts, cron jobs, logic)
  *Dry-run or sandbox validation where available.*
- [ ] **Tier 4 — Auto-Commit** (CLAUDE.md, READMEs, comments, frontmatter)
  *Full autonomy.*

---

## Services affected

<!--
List services whose operation could be affected by this change.
Check service-inventory.json for dependency relationships.
-->

| Service | Dependency type | Health check |
|---|---|---|
| | | |

---

## Pre-flight checklist

<!--
Required for Tier 0 and Tier 1. Recommended for Tier 2.
Reference: docs/runbooks/governance/pre-flight-checklist.md
-->

- [ ] Dependent services identified from service inventory
- [ ] Port/interface impact assessed
- [ ] Rollback procedure defined (see below)
- [ ] Kent is present and available to respond to issues
- [ ] Recent Restic backup confirmed (Tier 2+)

---

## Change description

**What will be modified:**

**Exact scope** (what is NOT changing):

---

## Rollback plan

<!--
If this change causes an outage, how do we reverse it?
Must be specific enough to execute under pressure.
-->

---

## Post-change verification

<!--
How will we confirm the change succeeded and nothing broke?
Reference: docs/runbooks/governance/post-change-verification.md
-->

- [ ] Primary service health check passes: `[command]`
- [ ] Dependent services verified:
  - [ ] [service 1]
  - [ ] [service 2]
- [ ] No errors in logs for 5 minutes post-change

---

## Architecture documentation updates

| File | Change |
|---|---|
| `data/service-inventory.json` | |
| `data/network-topology.json` | |

- [ ] JSON files updated with `updated_by` set to this issue number
- [ ] Markdown views match JSON sources

---

## Success criteria

- [ ] Change applied without service disruption
- [ ] All post-change verification steps pass
- [ ] Architecture docs updated
- [ ] Postmortem filed if any unplanned outage occurred during change

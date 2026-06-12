---
name: Infra
about: Infrastructure change — server, networking, credentials, hardware, config
title: "Infra: "
labels: P3-candidate, spec: brief
assignees: ''
---

<!--
SPEC LIFECYCLE (3 labels, auto-managed):
  1. "spec: brief" (default) — capture the idea. Fill in what you know.
  2. "spec: pending" — auto-added when promoted to P1/P2.
  3. "spec: ready" — manually applied when body is complete. Required for spec-kitty.

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

## Rebaseline obligation (#557)

<!--
Independent of tier. Consult docs/design/architecture/data/audited-surfaces.json.
-->

- [ ] This change touches an audited surface (openclaw agent prompts, openclaw config, systemd user units + deploy scripts, Python deps, Docker stack, committed SSH keys) — `Yes` / `No`
- [ ] If `Yes`: merge commit will record `Rebaseline: completed at <ts>` or `Rebaseline: not required — <reason>` per `docs/runbooks/security-baseline-ops.md`

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

## Deploy required?

- [ ] This change requires a deploy to office2 (most infra changes do)
- If yes: the plan MUST include a `deploys/queued/<name>.yaml` manifest entry per [`docs/runbooks/deploy/discipline.md`](../../docs/runbooks/deploy/discipline.md)

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

---

## Spec-ready criteria

<!--
Self-check before applying `spec: ready`. Until all items below are true,
leave at `spec: brief`. Phone-filed and capture-first issues are not
expected to meet this bar at file time — spec-readiness work happens at
the laptop when the issue is prioritized for /spec-kitty.specify.
-->

This issue qualifies for the `spec: ready` label when:

- [ ] **Summary** clearly states what is changing and why
- [ ] **Risk tier** is selected (exactly one box checked)
- [ ] **Services affected** lists dependents from `service-inventory.json` (or affirms "none")
- [ ] **Pre-flight checklist** items appropriate to the tier are addressed
- [ ] **Change description** is specific enough that an operator could execute it
- [ ] **Rollback plan** is concrete enough to execute under pressure
- [ ] **Post-change verification** includes named health checks for affected services
- [ ] **Architecture documentation updates** lists JSON files to update (or affirms none)
- [ ] **Supply-chain review** — if this change adds a new package source (brew tap, pip index, npm registry, MCP plugin / AI extension with system access), the body documents the dependency-tree review and pinning posture
- [ ] **Design-time discipline** — deterministic-vs-stochastic split has been considered; helper-script extraction is identified where appropriate (per Felix Constitution Directive 6 and the approved [helper-script conventions](../../docs/design/helper-script-conventions.md))
- [ ] **Helper / library / skill decision** — for any deterministic work this change introduces, the choice between agent-co-located helper, domain-co-located helper, shared library (`scripts/lib/`), or skill (`~/.openclaw/skills/`) has been made per the invocation-surface test in [helper-script-conventions § 9](../../docs/design/helper-script-conventions.md) (or the body explicitly affirms no new deterministic work is introduced)
- [ ] **Rebaseline obligation** answered (#557) — `Yes / No` per `docs/design/architecture/data/audited-surfaces.json`; if `Yes`, merge-commit rebaseline-record expected per `docs/runbooks/security-baseline-ops.md`
- [ ] HTML comment guidance blocks have been removed

---
work_package_id: WP07
title: Docs + coherence
dependencies:
- WP04
- WP05
- WP06
requirement_refs:
- FR-008
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
- T032
- T033
agent: "claude"
shell_pid: "73281"
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks/canary-registry-ops.md
create_intent:
- docs/runbooks/canary-registry-ops.md
execution_mode: code_change
owned_files:
- docs/runbooks/canary-registry-ops.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
- docs/design/coherence/decisions.jsonl
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load curator-carla`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Make the new canary registry **discoverable and doctrine-consistent**: write the operational runbook,
register it in the navigation docs, and record the coherence decision. This is the mission's documentation
close-out (the architecture JSON itself is edited by WP05 — do NOT touch `service-inventory.json` here).

Read first: `../spec.md`, `../quickstart.md` (Ops section), `../plan.md` IC-07, and the sibling runbook
`docs/runbooks/restic-backup-ops.md` for house style. Consult
`docs/design/architecture/data/signal-to-doc-map.json` (per CLAUDE.md's discovery aid) to confirm which
navigation/architecture docs a service-addition must touch — at minimum `docs/INDEX.md` and
`docs/DEVELOPER_PORTAL.md` (the precedent #492 codified). Read `docs/design/coherence/doctrine.md` (INV-003
= one canonical alert stream) and the format of `docs/design/coherence/decisions.jsonl`.

## Context

- **Runbook home**: `docs/runbooks/canary-registry-ops.md`. It documents WHERE the canary runs (office2
  `systemd --user` timer, 15-min), the state files (`/data/services/felix-canary/state/{dedup,last-tick}.json`
  and `/data/services/felix-canary/ledger/<date>.jsonl`), how to read the tick-signal, how to add/adjust a
  canary (declare a `health_check` + `max_age_seconds` in `service-inventory.json`), how to **silence** a
  component (suspend it — ADR-0006), and how to interpret coverage-gap / persistent-unknown alerts.
- **Coherence**: the canary registry is a new alert producer; it must emit ONLY via the #701 bus (INV-003).
  Record the decision that health-watching is a sibling scanner to `felix-trust-scan`, not an extension
  (mirrors research R1 + decision DM-01KX8TY1KRNXQ2Y7C6QKXYEYCR).
- **Docs frontmatter**: follow the repo's YAML front-matter convention (`id, doc_type, title, status,
  level, owners, last_validated, version`) — copy the shape from a recent runbook.

## Subtasks

### T030 — `docs/runbooks/canary-registry-ops.md`
- Sections: Overview (what/why, links to spec + ADR-0006 + #701); Where it runs (unit names, cadence,
  `OnFailure` shim); State & ledger files (paths, schemas, atomic-write note); Reading a tick
  (`last-tick.json` fields; the per-component ledger); Adding/adjusting a canary (health_check +
  `max_age_seconds`; the freshness vs liveness distinction); Silencing (suspend the component — never a
  code change); Alert types (stale/failed/degraded/coverage-gap/persistent-unknown/recovery) + severities;
  Troubleshooting (dead timer → #269 boundary; a stuck unknown → what it means); Self-observability boundary
  (crash → `OnFailure`; dead-timer → #269, deferred). Keep it operational and concrete.

### T031 — Navigation registration
- Add the runbook to `docs/INDEX.md` (runbooks group, with its Divio type annotation) and
  `docs/DEVELOPER_PORTAL.md` (wherever monitoring/operational runbooks are surfaced). Match the surrounding
  entry format exactly.

### T032 — Coherence record
- Append a `decisions.jsonl` entry recording: the canary registry as a new #701-bus producer honoring
  INV-003 (one canonical alert stream); the sibling-scanner (not extend-trust-scan) decision and its
  single-responsibility rationale. Match the existing JSONL schema (read a couple of existing lines first).
- If `doctrine.md` maintains an inventory of alert producers or INV-003 consumers, add the canary there;
  otherwise leave `doctrine.md` untouched (do not restructure it).

### T033 — Architecture-doc alignment
- Per the standing architecture-docs requirement (CLAUDE.md) and `signal-to-doc-map.json`, verify the
  service-addition is reflected in the architecture **narrative** views (not the JSON — WP05 owns that).
  If a services narrative/`.view.md` enumerates timers/services, add `felix-canary`. If the only
  authoritative surface is the JSON (already handled in WP05) and no narrative view enumerates services,
  record that finding in the mission notes and skip — do not invent a doc surface. Keep this scoped: docs
  only, no inventory JSON edits.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] `docs/runbooks/canary-registry-ops.md` covers run location, state/ledger files, adding/silencing a
      canary, alert types, and the #269 self-observability boundary.
- [ ] Runbook linked from `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`.
- [ ] A `coherence/decisions.jsonl` line records the #701-bus/INV-003 producer + sibling-scanner decision;
      the file still parses (one JSON object per line).
- [ ] No edits to `service-inventory.json` (WP05 owns it); Docs CI green.

## Reviewer guidance

Verify: the runbook is operational (an on-call reader can find the state files, read a tick, and silence a
noisy component without reading code); INDEX + DEVELOPER_PORTAL actually link it (the #492 miss class);
`decisions.jsonl` remains valid line-delimited JSON; the self-observability boundary is stated honestly
(crash covered, dead-timer deferred to #269 — no over-claim); no inventory JSON touched here.

## Activity Log
- 2026-07-11T18:38:47Z – claude – shell_pid=73281 – Assigned agent via action command
- 2026-07-11T18:50:17Z – claude – shell_pid=73281 – WP07: runbook + INDEX/PORTAL + coherence DEC-007 + narrative row.
- 2026-07-11T18:50:24Z – user – shell_pid=73281 – APPROVE (reviewer-renata): all 5 DoD pass; runbook accurate vs shipped code; linked from INDEX+PORTAL; DEC-007 valid; no JSON edit.

---
work_package_id: WP02
title: Independent drift check + canary registration
dependencies:
- WP01
requirement_refs:
- FR-009
- FR-010
- FR-014
- NFR-003
- NFR-006
tracker_refs: []
planning_base_branch: feat/openclaw-skills-sync
merge_target_branch: feat/openclaw-skills-sync
branch_strategy: Planning artifacts for this mission were generated on feat/openclaw-skills-sync. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/openclaw-skills-sync unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
agent: "claude"
shell_pid: "88535"
shell_pid_created_at: "1784429630.771975"
history:
- '2026-07-19: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/enforcement/skills_drift_check.py
create_intent:
- scripts/openclaw/enforcement/skills_drift_check.py
- tests/openclaw/enforcement/test_skills_drift_check.py
execution_mode: code_change
owned_files:
- scripts/openclaw/enforcement/skills_drift_check.py
- tests/openclaw/enforcement/test_skills_drift_check.py
- scripts/canary/registry.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

## Objective

Build `scripts/openclaw/enforcement/skills_drift_check.py` — an **independent** drift observer
(NOT the sync's code path) that MD5-compares each repo `SKILL.md` against its deployed copy,
alert-only, and reports orphans. Register it (and a freshness check) as canary probes so it inherits
the canary's cadence + alert-dedup. This is the FR-009 mechanism — the sync's `--dry-run` is not.

**Why independent** (research D-4 / Codex #1 HIGH-3): the sync overwrites office2 every tick, so a
dry-run using the sync's own code is circular and can be masked by the next remediating tick. A
separate observer catches "sync reports success but deployed file still differs" and repo-removed
orphans.

**Read before coding**: this mission's `data-model.md` (drift-check contract) + `research.md` (D-4),
`scripts/canary/registry.py` and `probes.py` (how probes are declared — mirror an existing
`command`/`freshness` probe), and `scripts/openclaw/enforcement/drift_check.py` (sibling style; do
NOT reuse its agent baseline-manifest engine — skills have no baseline manifest).

### Subtask T007 — `skills_drift_check.py` comparator

**Purpose**: Deterministic repo↔deployed comparison, alert-only, with orphan detection.

- Runs **on office2** (where the canary runs); reads both sides locally:
  - repo side = the checkout `SKILL.md` (`<repo_root>/scripts/openclaw/skills/<skill>/SKILL.md`),
  - deployed side = `/home/claude/.openclaw/skills/<skill>/SKILL.md`.
- For each repo skill: `state = match | drift` from `md5(repo) == md5(deployed)` (missing deployed =
  drift). Ignore `*.backup*` entirely (FR-010).
- **Orphan detection (FR-014)**: enumerate deployed skill dirs; a deployed skill with no repo
  counterpart → `state = orphan` (alert-only; never delete — copy-only preserved). Ignore `*.backup*`.
- **Exit contract**: `0` = all match, no orphans; **non-zero** = any drift or orphan (the canary
  turns non-zero into a deduped alert). `--json` prints `[{skill, state, repo_md5, deployed_md5}]`.
- CLI: `python3 -m scripts.openclaw.enforcement.skills_drift_check [--json]`. Stdlib-only compare
  (reuse a local `sha256`/`md5` helper; may import `compute_md5` is NOT allowed across the deploy
  module — keep this independent; a tiny local hash is fine).
- Deterministic; no LLM (NFR-006); no remediation (alert-only, NFR-003).

### Subtask T008 — Register canary probes

**Purpose**: Give the drift check + freshness a scheduled, deduped home.

- In `scripts/canary/registry.py`, add:
  1. a **command** probe that runs `skills_drift_check` (module `-m` form) and treats non-zero as a
     failure the canary alerts on (mirror an existing `_probe_command` registration);
  2. a **freshness** probe on `/data/services/openclaw/deploy/skills-last-tick.json` with
     `max_age_seconds: 600` (mirror the agent-prompt-sync `last-tick.json` freshness registration).
- Only touch `probes.py` if a genuinely new probe kind is needed — prefer reusing
  `_probe_command` / `_probe_freshness`.
- Keep the registry entries consistent with the existing schema (id, kind, target, cadence, alert
  routing). Do not change other registry entries.

### Subtask T009 — Tests (test-first)

- Temp repo-skills dir + temp deployed dir. Cases: all match → exit 0, `[]`/all-match JSON; one
  diverged → exit non-zero + that skill `state:drift`; `*.backup*` sidecar present → ignored (not
  drift, not orphan); deployed skill with no repo dir → `state:orphan` + non-zero; missing deployed
  file → drift.
- If the canary registration is unit-testable (registry schema validation), assert the two new
  entries are well-formed; otherwise cover the comparator thoroughly and note the registry is
  exercised by the live canary dry-run at deploy (task 6).

## Branch Strategy

Planning on `feat/openclaw-skills-sync`; merge target `feat/openclaw-skills-sync`. Worktree per lane
from `lanes.json`. WP02 depends on WP01 but touches disjoint files (safe to lane in parallel with WP03).

## Definition of Done

- [ ] `skills_drift_check.py` runnable via `-m`; drift + orphan + backup-ignore + `--json` + exit
      contract all implemented and tested.
- [ ] Two canary probes registered (drift command + freshness) mirroring existing entries.
- [ ] `pytest tests/openclaw/enforcement/test_skills_drift_check.py` green; tests written first.
- [ ] Genuinely independent of `deploy_agent_skills.py` (no import of the sync's compare path).

## Risks / reviewer guidance

- Reviewer: confirm the check does NOT re-invoke the sync (independence is the whole point).
- Confirm orphan detection ignores `*.backup*` and never deletes.
- Confirm the freshness probe points at `skills-last-tick.json` (not the prompt-sync `last-tick.json`).

## Activity Log

- 2026-07-19T02:49:19Z – claude – shell_pid=86809 – Assigned agent via action command
- 2026-07-19T02:53:42Z – claude – shell_pid=86809 – Independent drift-check comparator + 16 tests; canary wiring via service-inventory health_check in WP04
- 2026-07-19T02:54:00Z – claude – shell_pid=88535 – Started review via action command
- 2026-07-19T02:54:23Z – user – shell_pid=88535 – Comparator reviewed: independent of sync, exit contract + orphan + backup-ignore covered by 16 tests; smoke green. Canary wiring in WP04.

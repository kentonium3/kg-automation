# Implementation Plan: OpenClaw Skills Deploy/Sync

**Branch**: `feat/openclaw-skills-sync` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/openclaw-skills-sync-01KXW1DQ/spec.md`
**Source issue**: kentonium3/kg-automation#775

## Summary

Build an auto-deploy sync that keeps the six OpenClaw agent **skills**
(`scripts/openclaw/skills/<skill>/SKILL.md`) faithful to the office2 deployed copies at
`/home/claude/.openclaw/skills/<skill>/SKILL.md`, plus an alert-only drift check — closing the
silent-drift gap (#563 class) for the skills surface. The mechanism is a **parallel module**
(`scripts/openclaw/deploy/deploy_agent_skills.py`) that reuses the proven `agent-prompt-sync`
(#567) discipline and the shared `scripts/deploy/lib/` primitives (`gitsync.advance_checkout`,
`deploylock`, `health.record`), with its own repo-derived scope, its own audit log + health
watermark + freshness signal, its own systemd user timer, and deployment through a
`deploys/queued/` manifest (DIR-004). Skill *content* is out of scope (#714).

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; stdlib for the core sync path)
**Primary Dependencies**: stdlib (`hashlib`, `os`, `json`, `argparse`, `pathlib`) + in-repo shared
libs `scripts/deploy/lib/{gitsync,deploylock,health}` and `scripts/common/alert_bus` (`emit(Alert)`).
No third-party packages (no requests/httpx/pydantic) — mirrors the prompt-sync constraint.
**Storage**: filesystem only — repo `SKILL.md` files (source of truth) → deployed `SKILL.md` files;
append-only JSONL audit log + JSON health-watermark + `last-tick.json` freshness pointer under
`/data/services/openclaw/deploy/`.
**Testing**: pytest, unit + integration, mirroring `tests/openclaw/deploy/` and `tests/deploy/`
patterns. Test-first (DIRECTIVE_034). Helper invoked as `python3 -m scripts.openclaw.deploy.deploy_agent_skills`
(the `-m` form — script-path invocation ModuleNotFoumdError trap, per repo memory + #668).
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS) as a systemd `--user` oneshot + timer under
user-linger; authored on Mac.
**Project Type**: single (Python helper + systemd units + deploy manifest + docs)
**Performance Goals**: a no-drift tick completes in <2s (6 small files); propagation ≤ one timer
interval (match agent-prompt-sync's 300s cadence).
**Constraints**: Tier 3; audited surface (systemd unit + deploy script) → rebaseline on merge;
Tailscale-only; deterministic runtime (no LLM); copy-only (no prune); repo is sole source of truth.
**Scale/Scope**: 6 skills × 1 `SKILL.md` each today; scope auto-derived from the repo skills dir so
new skills are picked up without code change.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Status | Note |
|-----------|--------|------|
| DIR-001 (production on office2) | ✅ | Deployed helper runs on office2; Mac is authoring only. |
| DIR-002 (Linux by default) | ✅ | systemd + python3; no Windows/Dropbox. |
| DIR-003 (Tailscale-only) | ✅ | No new exposure; office2-internal filesystem sync. |
| DIR-004 (manifest discipline) | ✅ | Deploy via `deploys/queued/skills-sync.yaml` → felix-deployer. |
| DIR-005 (safe-deploy order) | ✅ | Deploy script: pre-flight → place units/code → verify → enable. |
| DIR-007 (no system crontab) | ✅ | systemd `--user` timer, not crontab; and not an openclaw cron. |
| DIR-008 (real service paths) | ✅ | Dest path filesystem-verified (`/home/claude/.openclaw/skills/`); openclaw.json `skills` block is a *different* npm-plugin subsystem — NOT the target (see research D-2). |
| DIR-010 / DIRECTIVE_034 (test-first) | ✅ | Tests precede implementation per WP. |
| DIRECTIVE_024 (locality of change) | ✅ | Parallel module keeps blast radius off the load-bearing prompt-sync path. |
| DIR-014 (doc-sync requirement) | ✅ | Documentation Synchronization list in spec §; WP updates arch JSON+md+runbook+INDEX. |
| DIR-015 (probe real env at design) | ✅ | Probed office2 skills dirs, openclaw.json, health.record, systemctl --user context during plan. |
| #557 rebaseline | ✅ | Audited surface (systemd unit + deploy script) → merge records rebaseline outcome. |

No violations. No Complexity Tracking entries required.

## Key Design Decisions (see research.md for full rationale)

1. **Parallel module, not extend** (D-1). `deploy_agent_prompts.py` is tightly coupled to the
   agent-inventory scope model (`iter_agents`, `source_in_repo`/`workspace`, 5-file allowlist).
   Skills have a different scope (repo-dir enumeration, single `SKILL.md`, different dest base). A
   parallel `deploy_agent_skills.py` gives clean ownership (DIRECTIVE_024) and leaves the
   silently-failing-guard prompt path untouched. The two generic primitives it needs that currently
   live inside the prompt module (`compute_md5`, `atomic_copy`) are **duplicated locally** (~40
   trivial stdlib lines; two call sites is within the rule-of-three — extract a shared
   `_sync_common.py` only if a third consumer appears). The non-trivial shared primitives
   (`gitsync`, `deploylock`, `health`) are imported from `scripts/deploy/lib/` as-is.

2. **Alert via the felix-alert bus directly** (D-3). The health watermark's notifier seam
   (`health.record(..., notifier=)` calling `(title, body) -> bool`) dispatches through
   `scripts.common.alert_bus.emit(Alert(...))`, returning `result.delivered`. This is the canonical
   modern bus (prompt-sync's importlib load of felix-deployer `notify.py` is a documented vestigial
   wrapper over the *same* bus) — cleaner and no hyphenated-dir importlib dance.

3. **Drift check reuses the sync's own `--dry-run`** (D-4). The read-only `--dry-run` path already
   computes the authoritative repo↔office2 MD5 comparison and prints `DRIFT` lines. The drift check
   is that computation surfaced on a cadence/enforcement pass, alert-only, ignoring `*.backup*`
   (FR-010). It also registers skills in the existing enforcement surface
   (`drift-check-config.json`) **only if** skills fit the detection model cleanly; the
   baseline-manifest three-way-diff that `detection.py` uses is agent-specific, so the default is a
   self-contained skills drift report through the same alert bus rather than force-fitting skills
   into that model. (Flagged for the post-plan Codex review.)

4. **Deploy = queued manifest that places code+units + verifies; enable is a linger-aware step**
   (D-5). felix-deployer applies `deploys/queued/skills-sync.yaml`: pre-flight → confirm new code
   present in the checkout (arrives via the checkout's own self-advance in the merge) → copy
   `.service`/`.timer` into `~/.config/systemd/user/` → verify. The `systemctl --user enable --now`
   is performed with `XDG_RUNTIME_DIR=/run/user/$(id -u)` set (non-login ssh shows `--user` as
   `degraded`; the units run under user-linger). The manifest treats the enable as best-effort/
   non-fatal and the `.service`/`.timer` headers document the one-time operator/live enable
   (mirroring how agent-prompt-sync was enabled); the mission's live-verify step (task 6) confirms
   the timer is active.

## Project Structure

### Documentation (this mission)

```
kitty-specs/openclaw-skills-sync-01KXW1DQ/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions D-1…D-6
├── data-model.md        # Phase 1 output — entities + record shapes
├── quickstart.md        # Phase 1 output — deploy + live-verify runbook
└── tasks/               # /spec-kitty.tasks output (NOT created here)
```

### Source Code (repository root)

```
scripts/openclaw/deploy/
├── deploy_agent_skills.py            # NEW — the skills sync helper (parallel to deploy_agent_prompts.py)
├── agent-skill-sync.service          # NEW — systemd --user oneshot unit
├── agent-skill-sync.timer            # NEW — systemd --user timer (OnUnitInactiveSec=300s, OnBootSec, Persistent)
├── deploy_agent_prompts.py           # UNCHANGED (reference only)
├── agent-prompt-sync.service/.timer  # UNCHANGED (reference only)

scripts/openclaw/skills/<skill>/SKILL.md   # SOURCE OF TRUTH (unchanged content; sync reads these)

scripts/deploy/
├── deploy-skills-sync.sh             # NEW — manifest entrypoint (place units+verify, linger-aware enable)
└── lib/{gitsync,deploylock,health}.py   # REUSED as-is (imported)

scripts/openclaw/enforcement/
├── drift-check-config.json           # MODIFIED (only if skills fit cleanly — see D-4)

deploys/queued/
└── skills-sync.yaml                  # NEW — v1 manifest (tier 1/3, audited_surface: true)

tests/openclaw/deploy/
└── test_deploy_agent_skills.py       # NEW — unit + integration tests (test-first)

docs/runbooks/
└── agent-skill-sync-ops.md           # NEW — ops runbook (mirrors agent-prompt-sync-ops.md)

# Deployed (office2, not in repo): /home/claude/.openclaw/skills/<skill>/SKILL.md  (dest)
#                                  /data/services/openclaw/deploy/agent-skill-sync.jsonl (audit)
#                                  .../agent-skill-sync-health.json, .../skills-last-tick.json
```

**Structure Decision**: Parallel deploy module co-located with the existing openclaw deploy
mechanism, reusing the shared deploy library. New systemd units + deploy script + manifest follow
the agent-prompt-sync template verbatim so the two syncs are operationally symmetric.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Skills sync helper (core deterministic path)

- **Purpose**: Enumerate repo skills, MD5-compare against deployed copies, atomic-copy drift,
  emit audit + freshness + health signals, support `--dry-run` and `--skill <name>` filter.
- **Relevant requirements**: FR-001…FR-008, FR-011, NFR-001…NFR-006.
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_skills.py`; imports
  `scripts/deploy/lib/{gitsync,deploylock,health}`, `scripts/common/alert_bus`.
- **Sequencing/depends-on**: none (foundation).
- **Risks**: reuse the shared `deploylock` so the tick never races felix-deployer / prompt-sync on
  the checkout; `-m` invocation form; copy-only (never prune); exit-code contract mirrors prompt-sync.

### IC-02 — Drift check (alert-only)

- **Purpose**: Detect repo↔office2 skill divergence and alert (no remediation — the sync remediates),
  ignoring `*.backup*`.
- **Relevant requirements**: FR-009, FR-010, NFR-003.
- **Affected surfaces**: the helper's `--dry-run` drift computation; optionally
  `scripts/openclaw/enforcement/drift-check-config.json` (only if skills fit the model — D-4).
- **Sequencing/depends-on**: IC-01 (uses its drift computation).
- **Risks**: avoid force-fitting skills into the agent baseline-manifest three-way-diff; keep the
  skills drift report deterministic and alert-only.

### IC-03 — Systemd units + timer

- **Purpose**: Schedule the sync on office2 at the agent-prompt-sync cadence under user-linger.
- **Relevant requirements**: FR-008, NFR-001.
- **Affected surfaces**: `scripts/openclaw/deploy/agent-skill-sync.{service,timer}`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: `systemctl --user` needs `XDG_RUNTIME_DIR` in non-login contexts; document the enable.

### IC-04 — Deploy manifest + entrypoint

- **Purpose**: Roll the mechanism to office2 through the manifest pipeline (DIR-004), audited-surface
  aware, with the linger-aware enable and safe-deploy ordering (DIR-005).
- **Relevant requirements**: FR-012, C-002.
- **Affected surfaces**: `deploys/queued/skills-sync.yaml`, `scripts/deploy/deploy-skills-sync.sh`.
- **Sequencing/depends-on**: IC-01, IC-03.
- **Risks**: entrypoint must not hard-fail on a `systemctl --user` enable hiccup (would fail the
  felix-deployer apply + alert); code presence must be verified before unit enable.

### IC-05 — Documentation synchronization

- **Purpose**: Register the new service/unit/data-flow and the ops runbook across the arch docs.
- **Relevant requirements**: FR-013, DIR-014.
- **Affected surfaces**: `service-inventory.json`+`.md`, `service-dependencies.view.md`,
  `audited-surfaces.json`, `data-flows.json`+`.md`+`.view.md`, `docs/runbooks/agent-skill-sync-ops.md`,
  `docs/runbooks/deployment.md`, `docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`, roadmap note.
- **Sequencing/depends-on**: IC-01…IC-04 (documents what they build).
- **Risks**: keep JSON authoritative + markdown views in sync; `updated_by: 775`.

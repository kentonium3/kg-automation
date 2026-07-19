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
   `scripts.common.alert_bus.emit(Alert(source=…, severity=…, title=…, description=…))` and returns
   **`result.ok`** (the `AlertResult` field is `.ok`, **not** `.delivered` — verified in `model.py`;
   using `.delivered` would raise `AttributeError`, be swallowed by `health.record`, and silently
   never alert). `Alert` requires `source, severity, title, description` (+ optional `action`,
   `details`). This is the canonical modern bus (prompt-sync's importlib load of felix-deployer
   `notify.py` is a documented vestigial wrapper over the *same* bus). *(Codex #1 HIGH-2.)*

3. **Drift check = an INDEPENDENT canary probe, not the sync's own `--dry-run`** (D-4). The sync's
   `--dry-run` shares the sync's code path and — because the sync overwrites office2 every tick — a
   dry-run would be partly circular and could be masked by the next remediating tick. Instead, a
   standalone comparator `scripts/openclaw/enforcement/skills_drift_check.py` (independent of
   `deploy_agent_skills.py`) directly MD5-compares each checkout-repo `SKILL.md` against its deployed
   copy, alert-only, ignoring `*.backup*` (FR-010), and reports **orphans** — deployed skills with no
   repo counterpart (FR-014). It is registered as a **canary probe** (`scripts/canary/registry.py` +
   `probes.py`, the established independent-observer surface, #327) so it inherits the canary's
   cadence + alert-dedup. The `--dry-run` on the sync remains an operator convenience, not the
   FR-009 mechanism. *(Codex #1 HIGH-3.)*

4. **Deploy = queued manifest with a HARD verify-before-enable gate** (D-5). felix-deployer applies
   `deploys/queued/skills-sync.yaml`: pre-flight → confirm new code present in the checkout (arrives
   via the checkout self-advance in the merge) → copy `.service`/`.timer` into
   `~/.config/systemd/user/` → `systemctl --user daemon-reload` → **run the real unit once**
   (`systemctl --user start agent-skill-sync.service`) and assert it wrote `skills-last-tick.json`
   (the smoke gate) → **only then** `enable --now` → assert `is-enabled` + `list-timers` shows the
   timer. `systemctl --user` **works** from the deploy pipeline (precedent: `deploy-felix-canary.py`,
   `deploy-habits-weekly-driver.py`), exporting `XDG_RUNTIME_DIR=/run/user/$(id -u)`. A failed
   smoke/enable **fails the deploy loudly** (felix-deployer marks it failed + alerts) — it is NOT
   best-effort, because an installed-but-not-running timer is exactly the stranded-edit failure this
   mission exists to eliminate. *(Codex #1 HIGH-1.)*

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
├── skills_drift_check.py             # NEW — independent repo↔deployed MD5 comparator (drift + orphans), alert-only

scripts/canary/
├── registry.py                       # MODIFIED — register skills-drift + skills-freshness probes
├── probes.py                         # MODIFIED only if a new probe kind is needed (else reuse _probe_command/_probe_freshness)

docs/design/architecture/data/
├── audited-surfaces.json             # MODIFIED — extend globs to cover the new unit + deploy script (Codex #1 MEDIUM-1)

deploys/queued/
└── skills-sync.yaml                  # NEW — v1 manifest (tier: 3, audited_surface: true)

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

- **Purpose**: Enumerate repo skills, MD5-compare against deployed copies, atomic-copy drift
  (creating `dest.parent` first — FR-016), emit audit + freshness + health signals, warning-audit a
  multi-file skill dir (FR-015), support `--dry-run` and `--skill <name>` filter.
- **Relevant requirements**: FR-001…FR-008, FR-011, FR-015, FR-016, NFR-001…NFR-006.
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_skills.py`; imports
  `scripts/deploy/lib/{gitsync,deploylock,health}`, `scripts/common/alert_bus` (notifier returns
  `emit(Alert(...)).ok`).
- **Sequencing/depends-on**: none (foundation).
- **Risks**: reuse the shared `deploylock` so the tick never races felix-deployer / prompt-sync on
  the checkout; `-m` invocation form; copy-only (never prune); exit-code contract mirrors prompt-sync.

### IC-02 — Independent drift check (alert-only)

- **Purpose**: A standalone comparator (`scripts/openclaw/enforcement/skills_drift_check.py`),
  independent of the sync code path, that MD5-compares repo↔deployed per skill and alerts — including
  orphan detection (deployed skill absent from repo, FR-014) — ignoring `*.backup*`. Registered as a
  canary probe for cadence + dedup.
- **Relevant requirements**: FR-009, FR-010, FR-014, NFR-003.
- **Affected surfaces**: `scripts/openclaw/enforcement/skills_drift_check.py`,
  `scripts/canary/registry.py` (+ `probes.py` only if a new probe kind is needed).
- **Sequencing/depends-on**: none for the comparator; the canary registration references the freshness
  signal IC-01 emits.
- **Risks**: must be genuinely independent (not re-invoke the sync); deterministic; alert-only.

### IC-03 — Systemd units + timer

- **Purpose**: Schedule the sync on office2 at the agent-prompt-sync cadence under user-linger.
- **Relevant requirements**: FR-008, NFR-001.
- **Affected surfaces**: `scripts/openclaw/deploy/agent-skill-sync.{service,timer}`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: `systemctl --user` needs `XDG_RUNTIME_DIR` in non-login contexts (handled in the deploy
  entrypoint per precedent).

### IC-04 — Deploy manifest + entrypoint (hard verify-before-enable gate)

- **Purpose**: Roll the mechanism to office2 through the manifest pipeline (DIR-004), audited-surface
  aware, with a HARD enable gate + safe-deploy ordering (DIR-005): daemon-reload → real-unit smoke
  (freshness signal written) → enable --now → assert is-enabled/list-timers. A failed smoke/enable
  fails the deploy loudly.
- **Relevant requirements**: FR-012, C-002.
- **Affected surfaces**: `deploys/queued/skills-sync.yaml`, `scripts/deploy/deploy-skills-sync.sh`.
- **Sequencing/depends-on**: IC-01, IC-03.
- **Risks**: an installed-but-not-running timer silently defeats the mission — the enable must NOT be
  best-effort; export `XDG_RUNTIME_DIR`; verify the smoke before enable (mirror `deploy-felix-canary.py`).

### IC-05 — Documentation synchronization

- **Purpose**: Register the new service/unit/data-flow and the ops runbook across the arch docs.
- **Relevant requirements**: FR-013, DIR-014.
- **Affected surfaces**: `service-inventory.json`+`.md` (new service + its `skills-last-tick.json`
  health_check: endpoint `/data/services/openclaw/deploy/skills-last-tick.json`, tick-signal method,
  `max_age_seconds: 600`), `service-dependencies.view.md`, `audited-surfaces.json`
  (**extend globs** to cover `scripts/openclaw/deploy/*.{service,timer}` +
  `scripts/deploy/deploy-skills-sync.sh` — Codex #1 MEDIUM-1), `data-flows.json`+`.md`+`.view.md`,
  `docs/runbooks/agent-skill-sync-ops.md`, `docs/runbooks/deployment.md`, `docs/INDEX.md`,
  `docs/DEVELOPER_PORTAL.md`, roadmap note.
- **Sequencing/depends-on**: IC-01…IC-04 (documents what they build).
- **Risks**: keep JSON authoritative + markdown views in sync; `updated_by: 775`; the
  audited-surfaces glob extension is what makes the C-002 rebaseline claim true (verify with
  `validate_architecture_data`).

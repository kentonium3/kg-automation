# Implementation Plan: Agent Prompt Deploy Pipeline

**Branch**: `kitty/mission-agent-prompt-deploy-pipeline-01KTMDDD`
**Date**: 2026-06-08
**Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/agent-prompt-deploy-pipeline-01KTMDDD/spec.md`

## Summary

Build a stdlib Python helper invoked by a user-level systemd timer on office2. Each 5-minute tick performs `git pull --ff-only` inside `/home/claude/kg-automation`, then iterates the Felix agent inventory from `service-inventory.json`, MD5-compares each in-scope prompt file (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`) against its deployed counterpart at `<workspace>/<filename>`, and atomically copies any drifted file. Append-only JSONL audit log + per-tick summary at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. No openclaw restart triggered. Architecture follows the existing `scripts/sync/` precedent (felix-vikunja-sync driver) at smaller scale.

## Technical Context

**Language/Version**: Python 3.10+ (matches office2 system python at `/usr/bin/python3`; all current Felix helpers gate at 3.10+)
**Primary Dependencies**: Standard library only — `pathlib`, `hashlib`, `subprocess`, `json`, `argparse`, `tempfile`, `os`, `uuid`, `datetime`, `sys`. NO `requests`, `httpx`, `pydantic`, or any third-party package (per NFR-002 + kg-automation convention).
**Storage**: File system only. Source files at `/home/claude/kg-automation/scripts/openclaw/agents/<slug>/`; deployed files at `/data/services/openclaw/<deploy-dir>/`; audit log at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. Authoritative agent metadata read from `docs/design/architecture/data/service-inventory.json`. No database, no key-value store.
**Testing**: pytest with `pytest-cov`. Unit tests under `tests/openclaw/test_deploy_agent_prompts.py`. Coverage gate: ≥90% line, ≥85% branch (per NFR-003 and recent precedent in `vikunja-client-and-habits-weekly-report-01KTKSFT`). All I/O paths use `tmp_path` fixtures and subprocess mocking — no SSH, no real `/data/services/`, no real git. Production verification is operator-driven post-merge (per SC-1/SC-4).
**Target Platform**: office2 (Ubuntu 24.04 LTS), Linux user-level systemd. Helper runs as the `claude` user (no sudo).
**Project Type**: Single project (kg-automation repo; scripts under `scripts/`, tests under `tests/`).
**Performance Goals**: Per NFR-001 — a no-drift tick completes in <2 sec wall time. Steady-state has 5 agents × 5 files = 25 MD5 comparisons per tick. Drift days (one or two affected files) add ≤100ms of atomic-copy time per file. Headroom is comfortable.
**Constraints**: No sudo (C-001), no HEARTBEAT.md / GOVERNANCE.md / .tmpl / .bak* touches (C-002/003/004), `git pull --ff-only` only (C-005), no `.github/workflows/` modifications (C-006), Risk Tier 3 (C-007).
**Scale/Scope**: 5 in-scope Felix agents at design time (felix-admin-capture, felix-admin-habits, felix-admin-tasker, felix-admin-escalation, main). Auto-extends as agents are added to `services[openclaw].agents.*`. Per-agent files capped at the In-Scope Filename Set (5 filenames). Audit log grows ~6 lines/hour steady-state; no rotation in scope.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter loaded in compact mode for the `plan` action. The full charter and active directives are at `.kittify/doctrine/`. Relevant gates verified against the plan:

| Directive | Applicability | Status |
|---|---|---|
| **DIRECTIVE_001** Architectural Integrity | Helper has clear component boundaries (Discovery / Drift Detection / Git Pull / Audit Log / CLI). Each is testable in isolation. | PASS |
| **DIRECTIVE_010** Specification Fidelity | Plan maps directly to spec's FRs (FR-001..017), NFRs, and Cs. No drift between intent and implementation surface. | PASS |
| **DIRECTIVE_024** Locality of Change | Helper lives under `scripts/openclaw/deploy/` — co-located with the openclaw domain it serves. Systemd units co-located. Tests under `tests/openclaw/`. No cross-domain reach. | PASS |
| **DIRECTIVE_033** Targeted Staging Policy | Implementation commits will stage only the deliverables of each WP (helper module, unit files, tests, arch-doc updates as scheduled). | PASS (enforced at WP commit time) |
| **DIRECTIVE_034** Test-First Development | Each WP that delivers code starts with the test scaffolding (test file + fixtures) before the production module. | PASS (enforced at WP execution time) |
| **DIR-005** Mission spec must include doc-sync requirement | spec.md § Architecture Documentation Updates lists 5 doc surfaces. Plan inherits this. | PASS |
| **DIR-006** Probe real environment during design | Done extensively during specify (HEARTBEAT.md asymmetry, ownership variance, .tmpl exclusion, office2 clone state, existing systemd timer template) and reaffirmed here (no service-inventory reader exists; `scripts/sync/` is the structural template; `scripts/openclaw/deploy/` is the right home). | PASS |

No gate violations. Complexity Tracking section below is intentionally empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/agent-prompt-deploy-pipeline-01KTMDDD/
├── spec.md                # Mission spec (committed)
├── plan.md                # This file
├── meta.json              # Mission identity (committed)
├── research.md            # Phase 0 output
├── data-model.md          # Phase 1 output
├── quickstart.md          # Phase 1 output
├── contracts/             # Phase 1 output
│   ├── helper-cli.md
│   └── audit-log-jsonl.md
├── checklists/
│   └── requirements.md    # Spec quality checklist (committed)
└── tasks/
    └── README.md          # Scaffolded by mission create
```

### Source Code (repository root)

```
scripts/openclaw/deploy/                          # NEW (this mission)
├── __init__.py
├── deploy_agent_prompts.py                       # Helper module (CLI + functions)
├── agent-prompt-sync.service                     # systemd user oneshot unit
└── agent-prompt-sync.timer                       # systemd user timer

tests/openclaw/                                   # EXISTS
└── test_deploy_agent_prompts.py                  # NEW (this mission)

docs/design/architecture/data/                    # MODIFY
├── service-inventory.json                        # Add agent-prompt-sync top-level entry + main.source_in_repo
└── signal-to-doc-map.json                        # Add/extend agent-prompt-changed change_class

docs/design/architecture/                         # MODIFY
└── service-inventory.md                          # Add "Agent Prompt Deploy Pipeline" narrative section

docs/runbooks/                                    # ADD + MODIFY
├── agent-prompt-sync-ops.md                      # NEW operator runbook
└── openclaw-agent-setup.md                       # MODIFY: add "Deploy pipeline" section
```

**Structure Decision**: Single-project layout — no `src/` (kg-automation is a script collection, not a packaged library). Helper module is single-file; pure functions plus an orchestrator and CLI entry. Tests mirror the module in `tests/openclaw/`. Systemd unit files live alongside the helper (flat layout, matching the per-agent-helper precedent at `scripts/office2/felix-doc-auditor.{timer,service}`; `scripts/sync/systemd/` uses a sub-directory only because it has more units to organize). This decision honors **DIRECTIVE_024 Locality of Change**: all deploy-pipeline surfaces live under `scripts/openclaw/deploy/`.

## Complexity Tracking

*Empty — no Charter Check violations.*

## Implementation Concern Map

The mission has 8 distinct architectural concerns. `/spec-kitty.tasks` will translate these into work packages (one IC may become 1-2 WPs; small ICs may merge).

### IC-01 — Inventory Discovery & Filename Filtering

- **Purpose**: Read `service-inventory.json`, project the agent inventory down to the minimal `AgentInventoryEntry` shape used by the rest of the helper, and apply the in-scope / excluded filename filters.
- **Relevant requirements**: FR-001, FR-002, C-002, C-003, C-004
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (functions `iter_agents`, `is_in_scope`, `iter_source_files`)
- **Sequencing/depends-on**: none (foundational)
- **Risks**: Schema drift in `service-inventory.json` — current schema has `services[openclaw].agents.<slug>.{source_in_repo, workspace}`; a schema change would break the reader. Mitigation: validate required fields per-agent, log warning + skip on missing field rather than crashing the whole tick.

### IC-02 — Drift Detection & Atomic Copy

- **Purpose**: Compute MD5 of source and destination, copy with `os.replace` when drifted, preserve destination mode if it existed, write-temp-then-rename.
- **Relevant requirements**: FR-003, FR-004, FR-005, FR-016, NFR-006
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (functions `compute_md5`, `atomic_copy`, `sync_agent`)
- **Sequencing/depends-on**: IC-01 (inventory is the input)
- **Risks**: Disk-full mid-write leaves the temp file behind; `os.replace` failure should not corrupt the destination. Test with `tmp_path` and a custom mock raising `OSError` from `os.replace`. Permission mismatch (helper writes as `claude:claude` even on dirs where existing files are `claude:felix`): plan preserves MODE only, ownership stays as whatever the helper-user produces. Document in runbook; not in scope to chown.

### IC-03 — Git Pull Wrapper

- **Purpose**: Run `git fetch && git pull --ff-only origin main` inside `/home/claude/kg-automation`. On failure, log structured `git_pull_failed` entry and exit with code 2 without copying anything.
- **Relevant requirements**: FR-006, FR-010 (exit code 2), C-005
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (function `git_pull`)
- **Sequencing/depends-on**: none (precedes IC-01/IC-02 at run time, but is independent in code)
- **Risks**: Network blip can fail the pull. Mitigation: deterministic exit with code 2; next tick is a free retry. Branch divergence (e.g., manual edit on office2) causes `--ff-only` to fail; mitigation: log and bail; operator handles divergence manually.

### IC-04 — Audit Log

- **Purpose**: Append-only JSONL at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. One entry per file action (copy / skip / error / git_pull_failed) plus one summary entry per tick.
- **Relevant requirements**: FR-009, FR-015, NFR-004
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (functions `audit_record`, `audit_append`, `audit_tick_summary`, dataclass `SyncAction`, dataclass `TickSummary`)
- **Sequencing/depends-on**: IC-02 emits the per-file records; IC-03 emits the git-pull-failed record; CLI orchestrator emits the tick summary
- **Risks**: Log directory may not exist on first run. Mitigation: `Path.mkdir(parents=True, exist_ok=True)` per FR-015. Log file unbounded growth: documented in spec Out of Scope; logrotate is operator's call later.

### IC-05 — CLI Surface

- **Purpose**: Argparse entry-point with `--dry-run` and `--agent <slug>` flags. Orchestrates IC-03 → IC-01 → IC-02 → IC-04 per-tick. Returns the documented exit codes (0/1/2).
- **Relevant requirements**: FR-007, FR-008, FR-010, NFR-005, NFR-006
- **Affected surfaces**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (functions `parse_args`, `run_tick`, `main`)
- **Sequencing/depends-on**: IC-01, IC-02, IC-03, IC-04 (orchestrates them all)
- **Risks**: argparse edge cases on multi-flag combinations (`--dry-run --agent felix-admin-capture`). Mitigation: explicit test cases.

### IC-06 — Systemd Unit Files & Operator Surface

- **Purpose**: Author `agent-prompt-sync.timer` and `agent-prompt-sync.service` modeled on `felix-vikunja-sync.{timer,service}`. Document the one-time deploy procedure.
- **Relevant requirements**: FR-011, FR-012, FR-013, NFR-005
- **Affected surfaces**: `scripts/openclaw/deploy/agent-prompt-sync.{timer,service}`, runbook updates
- **Sequencing/depends-on**: IC-05 (the service unit invokes the helper)
- **Risks**: Unit-file syntax errors cause silent fail at `systemctl --user daemon-reload` time. Mitigation: copy verbatim from the working felix-vikunja-sync precedent; have operator validate with `systemctl --user status agent-prompt-sync.timer` post-install.

### IC-07 — Architecture Documentation Sync

- **Purpose**: Update `service-inventory.json` with a new top-level `agent-prompt-sync` service entry, add `main.source_in_repo` field, update `signal-to-doc-map.json`, add narrative to `service-inventory.md`, add `agent-prompt-sync-ops.md` runbook, update `openclaw-agent-setup.md`.
- **Relevant requirements**: FR-014, DIR-005, spec § Architecture Documentation Updates
- **Affected surfaces**: 5 doc files (3 JSON + 1 narrative + 2 runbooks)
- **Sequencing/depends-on**: IC-05 + IC-06 (docs describe the helper that exists)
- **Risks**: JSON validation gates in CI may reject schema additions. Mitigation: follow the existing service-entry schema pattern verbatim; run validation locally before commit.

### IC-08 — Test Surface

- **Purpose**: Unit tests for every pure function (`compute_md5`, `is_in_scope`, `iter_agents`, `parse_args`, `audit_record`). Integration tests for `run_tick` orchestrator with mocked `git_pull` and tempdir fakes for source / destination / audit-log paths. Coverage gate ≥90% line / ≥85% branch.
- **Relevant requirements**: NFR-003
- **Affected surfaces**: `tests/openclaw/test_deploy_agent_prompts.py`
- **Sequencing/depends-on**: tests are written FIRST per **DIRECTIVE_034 Test-First Development**, before each batch of production code in their respective WPs
- **Risks**: Mocking `subprocess.run` for git_pull can mis-test the real shell semantics. Mitigation: assert on argv list passed to subprocess and on parsed exit code; do NOT shell out in tests. The git-pull integration is verified at operator install time, not in CI.

## Architecture Documentation Updates (consolidated)

Per **DIR-005**, the following updates are part of the mission's deliverables (not deferred):

| File | Update | Owner WP (assigned by /spec-kitty.tasks) |
|---|---|---|
| `docs/design/architecture/data/service-inventory.json` | New top-level `agent-prompt-sync` service entry (type: `systemd-timer`, host: `office2`, schedule, exec_start, source_in_repo for the unit files, health_check pointing at the audit log). Update `services[openclaw].agents.main` to add `source_in_repo: "scripts/openclaw/agents/main/"`. Bump `last_updated` + extend `updated_by`. | IC-07 |
| `docs/design/architecture/data/signal-to-doc-map.json` | Add or extend a `change_class` entry for `agent-prompt-changed` mapping to the affected service-inventory entries. | IC-07 |
| `docs/design/architecture/service-inventory.md` | Add narrative section "Agent Prompt Deploy Pipeline" covering the pull architecture, slug→deploy-dir mapping rule, and manual install procedure. | IC-07 |
| `docs/runbooks/openclaw-agent-setup.md` | Add "Deploy pipeline" section; clarify subsequent prompt edits no longer require manual file copies after the one-time unit install. | IC-07 |
| `docs/runbooks/agent-prompt-sync-ops.md` | NEW runbook: install, dry-run, single-agent force-sync, reading the audit log, common failure modes, rollback. | IC-07 |

## Engineering Alignment

Confirmed planning decisions baked into this plan:

- **Single-file helper module** — `scripts/openclaw/deploy/deploy_agent_prompts.py`. Sub-300 LOC. Splitting (à la `scripts/sync/`) is premature for this scale.
- **No shared `scripts/common/service_inventory.py`** — none exists; introducing one is premature abstraction. Inline `json.load` + dict navigation is correct.
- **Tests use pytest + tmp_path; no SSH, no real systemd** — production verification is operator-driven post-merge per SC-1/SC-4.
- **Systemd unit files flat under `scripts/openclaw/deploy/`** — not under a `systemd/` subdir; matches `felix-doc-auditor.{timer,service}` precedent.
- **`git pull --ff-only` only** — never plain `git pull`; never `git merge`; never `git reset`. C-005 enforced.
- **Mode preserved, ownership not** — atomic copy preserves `os.stat().st_mode` but does not chown. Helper runs as `claude`; existing files with `claude:felix` ownership keep that ownership only if `os.replace` preserves it across the rename (which it does, because `os.replace` does NOT change ownership of the source temp file's metadata at destination). Tested in IC-02 with a mocked stat.

## Operator Install Procedure (also goes into the runbook)

One-time, post-merge:

```bash
ssh office2-claude
cd ~/kg-automation
git pull --ff-only origin main
mkdir -p ~/.config/systemd/user
cp scripts/openclaw/deploy/agent-prompt-sync.service ~/.config/systemd/user/
cp scripts/openclaw/deploy/agent-prompt-sync.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agent-prompt-sync.timer
systemctl --user list-timers | grep agent-prompt-sync
```

Initial dry-run for confidence:

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.deploy.deploy_agent_prompts --dry-run
```

Verification post-first-tick:

```bash
journalctl --user -u agent-prompt-sync.service --since "10 min ago" --no-pager
tail -50 /data/services/openclaw/deploy/agent-prompt-sync.jsonl
md5sum /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
       /data/services/openclaw/inbox-agent/AGENTS.md
```

## Reference Index

- Spec: [spec.md](./spec.md)
- Issue: kentonium3/kg-automation#567
- Structural precedent: `scripts/sync/driver.py`, `scripts/sync/systemd/felix-vikunja-sync.{service,timer}`
- Per-agent helper precedent: `scripts/office2/felix-doc-auditor.{timer,service}`
- Service-inventory schema: `docs/design/architecture/data/service-inventory.json` § `services[openclaw].agents.*`
- Memory references: `[[reference_office2_agent_deploy_paths]]`, `[[feedback_helper_m_invocation_form]]`, `[[feedback_architecture_docs_first]]`, `[[feedback_scripts_vs_llm]]`

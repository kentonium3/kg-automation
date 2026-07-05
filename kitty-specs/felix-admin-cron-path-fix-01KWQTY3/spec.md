# Specification: Felix-admin cron path robustness fix

**Mission**: felix-admin-cron-path-fix-01KWQTY3
**Type**: software-dev (bug fix)
**Source**: kentonium3/kg-automation#656 (P1-bug, area/felix-core)
**Status**: Draft — pending plan

## Overview

Felix's admin cron agents on office2 (run as the `claude` user through OpenClaw)
invoke deterministic helpers with `python3 -m scripts.<domain>.<helper>`. That
invocation form only resolves when the agent's working directory is the repo
root `/home/claude/kg-automation`; from any other directory it fails with
`ModuleNotFoundError: No module named 'scripts'`. The agents are instructed to
`cd` there (or simply told "working dir is …"), but they maintain working
directory across tool calls and drift out of it, so scheduled runs fail
intermittently and by chance of cwd.

Separately, the inbox-capture agent's dedup ledger (`inbox-routing.jsonl`) and
its forensic logs (`inbox-prescan-*.md`) are being written under a stray
`/home/claude/second-brain/` directory that is synced by nothing (no Obsidian
sync, no git), is absent from the architecture docs, and is a different tree
from the canonical vault at `/home/kgale/second-brain/notes/`. As a result the
dedup state lives in a non-canonical location and the forensic logs never reach
Kent's phone or Mac.

This mission (1) makes every `python3 -m scripts.*` invocation in the affected
agent prompts working-directory-independent through a guardrail — not a prose
instruction that agents can drift away from — and (2) relocates the dedup ledger
and forensic logs to their canonical, convention-matching homes, migrating the
live data safely and decommissioning the stray directory.

## User Scenarios & Testing

**Primary actor**: the Felix admin cron agents on office2 — `felix-admin-capture`
(inbox-7am/noon/5pm/10pm) and `felix-admin-escalation` (escalation-daily), plus
the other agents that invoke `-m scripts.*` (`felix-admin-habits`,
`felix-admin-tasker`). Secondary actor: Kent, who reads inbox forensic logs from
his phone/Mac via Obsidian sync.

### Scenario 1 — Cron run from a drifted working directory (primary)

- **Trigger**: `escalation-daily` fires at 08:00 ET; the agent's working
  directory is `/data/services/openclaw/escalation-agent` (not the repo root).
- **Today (bug)**: `python3 -m scripts.escalation.derive_state …` →
  `ModuleNotFoundError` → run status `error`. Because escalation is once-daily
  with no intra-day retry, **no overdue-task alerts go out that day**.
- **Desired**: the helper resolves regardless of working directory; the run
  succeeds and the overdue-task alert is produced.

### Scenario 2 — Intermittent inbox failure by cwd (primary)

- **Trigger**: `inbox-7am` fires; the agent happens to be sitting in
  `/home/kgale/second-brain` from a prior action.
- **Today (bug)**: `python3 -m scripts.inbox.prescan` → `ModuleNotFoundError` →
  run `error`, while `inbox-noon` and `inbox-5pm` (same agent, same config)
  succeed because they happened to be at the repo root. Failure is
  non-deterministic, driven purely by cwd.
- **Desired**: all four daily inbox runs succeed regardless of cwd.

### Scenario 3 — Kent reads a forensic log on his phone (secondary)

- **Trigger**: Kent wants to see why a note was routed a certain way and opens
  `agents/logs/` in Obsidian on his phone.
- **Today (bug)**: the `inbox-prescan-YYYY-MM-DD.md` log was written to
  `/home/claude/second-brain/agents/logs/`, which does not sync; Kent sees
  nothing.
- **Desired**: the log is under the canonical vault
  `/home/kgale/second-brain/agents/logs/` and syncs to his devices.

### Scenario 4 — Dedup ledger continuity across the migration (rule)

- **Trigger**: the dedup ledger is relocated while it holds live, same-day
  routing entries.
- **Invariant that must hold**: after relocation, the capture agent consults the
  migrated ledger and does **not** re-route or re-file any note that was already
  routed. No dedup or routing regression is introduced by the move.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Every `python3 -m scripts.*` invocation in the affected felix-admin agent prompts MUST resolve the `scripts` package regardless of the agent's current working directory, enforced by a mechanism that does not depend on the agent first changing directory or on a prose "working dir is X" instruction. | Draft |
| FR-002 | The fix in FR-001 MUST be applied to every felix-admin agent that invokes `python3 -m scripts.*`, determined by an exhaustive sweep of the agent prompt sources — not only to the two agents that failed on 2026-07-04. The plan MUST enumerate the final agent/module set (grounded so far: capture→`scripts.inbox`, escalation→`scripts.escalation`, habits→`scripts.habits`, tasker→`scripts.enrichment`; calendar to be confirmed or excluded). | Draft |
| FR-003 | Pre-existing per-agent cwd workarounds that FR-001 makes redundant MUST be removed in the same change so a single guardrail is the only mechanism — specifically the `cd /home/claude/kg-automation && …` prefixes and the "cwd matters / ModuleNotFoundError" prose warning in the habits agent prompt, and the "Working dir: /home/claude/kg-automation" prose line in the capture agent prompt. | Draft |
| FR-004 | The inbox dedup ledger `inbox-routing.jsonl` MUST be served from `/data/services/openclaw/state/`, matching the JSONL-state convention used by the other agents. All readers and writers of the ledger MUST be updated to the new location. | Draft |
| FR-005 | The existing live `inbox-routing.jsonl` MUST be migrated from `/home/claude/second-brain/agents/state/` to the new location with its contents preserved, such that no already-routed note is re-routed after the move. | Draft |
| FR-006 | Inbox forensic logs MUST be written to the canonical Obsidian-synced vault at `/home/kgale/second-brain/agents/logs/`. This requires fixing the hardcoded `DEFAULT_LOG_DIR` in `scripts/inbox/prescan.py` and removing the `~/second-brain`-relative ambiguity in the capture agent prompt template (which resolves to `/home/claude` for the claude-run agent). | Draft |
| FR-007 | The deployed capture-agent prompt surfaces MUST be internally consistent about the forensic-log and state locations — the `AGENTS.md`/`AGENTS.md.tmpl` and `TOOLS.md`/`TOOLS.md.tmpl` copies MUST agree, with no residual references to the stray `/home/claude/second-brain` path. | Draft |
| FR-008 | Existing historical forensic logs and any other live contents under `/home/claude/second-brain/` MUST be preserved into their new canonical locations, after which the stray `/home/claude/second-brain/` directory MUST be decommissioned and no writer MUST recreate it. | Draft |
| FR-009 | The stale reference to the second, out-of-date repo copy `~/repos/kg-automation/…/log_action.py` in the escalation agent prompt (pointing at an April-15 copy rather than `/home/claude/kg-automation`) MUST be corrected in the same sweep. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | Reliability of the affected cron jobs after the fix. | 5 or more consecutive `inbox-*` and `escalation-daily` cron runs complete with status `success` and zero `ModuleNotFoundError` occurrences in their run output. | Draft |
| NFR-002 | The FR-001 guardrail MUST NOT depend on runtime working directory, so its correctness is verifiable independently of where the agent happens to be. | A deterministic test invokes an affected helper via the guardrailed form from at least two distinct working directories (repo root and a non-repo directory) and both succeed. | Draft |
| NFR-003 | The change ships through the existing agent-prompt-sync + `deploys/queued/` manifest pipeline; no file under office2 is hand-edited. | The mission's deploy artifact is a `deploys/queued/<name>.yaml` manifest; office2 state and log migration is performed by the applier/manifest, not by an interactive SSH edit. | Draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Agent prompt files (`scripts/openclaw/agents/*/AGENTS.md*`, `TOOLS.md*`) are an audited surface. The mission's merge must satisfy the rebaseline obligation (record `Rebaseline: completed …` or `Rebaseline: not required — <reason>`), and see the known gap that agent-prompt AGENTS.md changes are not hashed by the current baseline (project #621) — the plan must state which applies. | Draft |
| C-002 | All changes flow through the source of truth `scripts/openclaw/agents/*` (+ `scripts/inbox/prescan.py`) and the deploy pipeline. Per the workflow rules, `.kittify/` and `kitty-specs/` are workflow-owned; office2 is never hand-edited to simulate the deploy. | Draft |
| C-003 | The ledger relocation (FR-004/FR-005) and log relocation (FR-006/FR-008) mutate application state on office2 and touch a service data directory — treat as at least a Tier-2 (snapshot-required) change: confirm a recent Restic backup (or trigger one) before the live migration. | Draft |
| C-004 | Canonical locations are fixed by Kent's decisions and existing convention, not open for redesign in this mission: dedup ledger → `/data/services/openclaw/state/`; forensic logs → `/home/kgale/second-brain/agents/logs/` (the `obsidian-sync` service syncs `/home/kgale/second-brain/notes`). | Draft |

## Success Criteria

- **SC-1**: Reproduction steps 1–2 from the issue (`python3 -m scripts.escalation.derive_state --help` from the escalation agent dir; `python3 -m scripts.inbox.prescan --help` from the vault dir) no longer produce `ModuleNotFoundError` — the helpers resolve from any working directory.
- **SC-2**: 5+ consecutive inbox and escalation cron runs complete successfully with no cwd-related failures.
- **SC-3**: `inbox-routing.jsonl` is served from `/data/services/openclaw/state/`, and no note that was already routed before the migration is re-routed after it.
- **SC-4**: New inbox forensic logs appear under `/home/kgale/second-brain/agents/logs/` and sync to Kent's devices.
- **SC-5**: The stray `/home/claude/second-brain/` directory is decommissioned (its live contents preserved first) and no agent or helper recreates it on subsequent runs.
- **SC-6**: The stale `~/repos/kg-automation` reference is gone from the escalation agent prompt.
- **SC-7**: No regression in inbox routing/dedup or escalation state after deploy.

## Key Entities

- **Dedup ledger** — `inbox-routing.jsonl`, append-only JSONL recording routed notes; consulted each tick to skip re-routing. Written by `scripts.inbox.append_routing_entry`; consumed by the prescan/dedup path. Current (wrong) home: `/home/claude/second-brain/agents/state/`; target home: `/data/services/openclaw/state/`.
- **Forensic log** — `inbox-prescan-YYYY-MM-DD.md`, human-readable per-run record of prescan decisions. Path currently set by `DEFAULT_LOG_DIR` in `scripts/inbox/prescan.py` and by the capture prompt template. Target home: `/home/kgale/second-brain/agents/logs/`.
- **Affected agent prompts** — `scripts/openclaw/agents/{felix-admin-capture,felix-admin-escalation,felix-admin-habits,felix-admin-tasker}/AGENTS.md[.tmpl]` (and capture `TOOLS.md[.tmpl]`); the source of truth that agent-prompt-sync deploys to office2.

## Assumptions

- The `scripts.enrichment` module (not `scripts.tasker`) is the correct package the tasker agent invokes; confirmed by grep of the agent prompt. The issue's "tasker" label refers to the `felix-admin-tasker` agent.
- `felix-admin-calendar` currently issues **no** `python3 -m scripts.*` invocation (grep found none); the plan will confirm and, if so, exclude it from the FR-002 sweep rather than invent a guardrail with nothing to guard.
- `felix-doc-auditor` is a scripts-first driver, not an OpenClaw prompt agent, and is out of scope unless the plan's sweep surfaces an in-prompt `-m scripts.*` invocation.
- The canonical vault path for logs is `/home/kgale/second-brain` because `obsidian-sync` syncs `/home/kgale/second-brain/notes`; `~` in the claude-run agent resolves to `/home/claude`, which is the root cause of the drift.

## Edge Cases

- The live `inbox-routing.jsonl` receives a new write between snapshot and cutover — the migration must not lose entries written during the window (append-safe / last-write-wins reconciliation, decided at plan).
- Both a stray-path log and a canonical-path log exist for the same day during rollout — avoid duplicate/split logs for a single date.
- An agent still holds the old prose "working dir" instruction from a cached session prompt after deploy — the guardrail must make the invocation correct even if the stale prose is still present (guardrail is load-bearing, prose is not).
- A reader of the ledger runs before the writer is updated (or vice versa) during deploy — reader/writer path changes must be consistent within the deployed set.

## Out of Scope

- Redesigning the helper invocation convention project-wide beyond the felix-admin agents that actually invoke `-m scripts.*`.
- Changing the canonical target locations (fixed by C-004).
- Any change to the doc-auditor driver, the OpenClaw core relocation (#653), or the WhatsApp DM-reply work (#652).
- Broader consolidation of the two repo checkouts on office2 beyond removing the single stale reference in FR-009.

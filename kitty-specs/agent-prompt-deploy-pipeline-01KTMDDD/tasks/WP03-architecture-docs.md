---
work_package_id: WP03
title: Architecture documentation sync
dependencies:
- WP01
- WP02
requirement_refs:
- FR-014
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
agent: "claude"
shell_pid: "2781"
history:
- timestamp: '2026-06-08T20:25:00Z'
  actor: claude
  event: Created via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KTMDDDGGY00S3S3VFGK0Z6P9
mission_slug: agent-prompt-deploy-pipeline-01KTMDDD
model: claude-sonnet-4-6
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/signal-to-doc-map.json
- docs/design/architecture/service-inventory.md
- docs/runbooks/openclaw-agent-setup.md
- docs/runbooks/agent-prompt-sync-ops.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

This sets up the curator posture: careful with cross-document references, accurate to current code, no speculative claims, no aspirational descriptions.

## Objective

Update all architecture documentation surfaces enumerated in [../spec.md](../spec.md) § Architecture Documentation Updates. Per **DIR-005**, every mission spec must include a doc-sync requirement and it ships with the feature, NOT deferred.

The surfaces:

| File | Update type |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Add new top-level service entry + backfill `main.source_in_repo` field |
| `docs/design/architecture/data/signal-to-doc-map.json` | Add `agent-prompt-changed` change_class entry |
| `docs/design/architecture/service-inventory.md` | New narrative section "Agent Prompt Deploy Pipeline" |
| `docs/runbooks/openclaw-agent-setup.md` | New section "Deploy pipeline" referencing the new helper |
| `docs/runbooks/agent-prompt-sync-ops.md` | NEW runbook (operator-facing) |

## Context — read these first

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § Architecture Documentation Updates | The canonical surface list and per-file update intent |
| [../quickstart.md](../quickstart.md) | Substantial content for the new agent-prompt-sync-ops.md runbook can be lifted from here |
| [../plan.md](../plan.md) § Architecture Documentation Updates | Per-WP assignment for each surface |
| `docs/design/architecture/data/service-inventory.json` (existing felix-doc-auditor entry) | Schema template for the new agent-prompt-sync entry |
| `docs/design/architecture/data/signal-to-doc-map.json` | Existing schema for change_class entries |
| `docs/design/architecture/service-inventory.md` | Style and depth of existing narrative sections |
| `docs/runbooks/openclaw-agent-setup.md` | Existing runbook structure to extend |
| `docs/runbooks/doc-auditor-driver-ops.md` | Existing per-service-runbook structure to mirror in the new sync-ops runbook |

## Branch Strategy

- **Planning base / merge target**: `main`
- **Coordination branch**: `kitty/mission-agent-prompt-deploy-pipeline-01KTMDDD`
- **Execution worktree**: `spec-kitty implement WP03 --agent claude` creates a lane worktree off the coordination branch (after WP01 + WP02 have merged into coordination).

## Subtask Guidance

### T011 — Update `service-inventory.json`

**Purpose**: Add a new top-level service entry for the agent-prompt-sync helper, plus backfill the `main` agent's `source_in_repo` field (which is currently missing despite the repo dir existing).

**Steps**:

1. Add a new entry to the `services` array, modeled on the existing `felix-doc-auditor` entry. Required fields:
   - `name`: `"agent-prompt-sync"`
   - `type`: `"systemd-timer"`
   - `host`: `"office2"`
   - `agent`: `"agent-prompt-sync"` (this is not an LLM agent; the field name is legacy from the systemd-timer schema)
   - `user`: `"claude"`
   - `systemd_unit`: `"agent-prompt-sync.timer (user unit) + agent-prompt-sync.service (user oneshot)"`
   - `systemd_user`: `"claude"`
   - `schedule`: `"OnUnitInactiveSec=300s + OnBootSec=120s + Persistent=true"`
   - `exec_start`: `"/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_prompts"` (use the -m form per NFR-005)
   - `exec_start_note`: `"Pull-based agent prompt sync. Each tick: git fetch + git pull --ff-only origin main inside /home/claude/kg-automation, then MD5-compare + atomic-copy any drifted agent prompt file from scripts/openclaw/agents/<slug>/ into /data/services/openclaw/<deploy-dir>/. No openclaw restart triggered."`
   - `timeout_seconds`: `120`
   - `session_mode`: `"stateless"`
   - `deployed_by`: `"#567"`
   - `status`: `"active"`
   - `purpose`: One-line purpose statement
   - `health_check`: object with `method: "tick-signal-file"`, `endpoint: "/data/services/openclaw/deploy/agent-prompt-sync.jsonl"`, `expected: "tick_summary entry with exit_code=0 within last 10 minutes"`, `timeout_seconds: 5`
   - `config_files`: array with entries for the timer and service files at their `~/.config/systemd/user/` deploy paths and `scripts/openclaw/deploy/...` source paths
2. Update the existing `services[<openclaw service>].agents.main` entry to add: `"source_in_repo": "scripts/openclaw/agents/main/"`. The main agent has source on disk (verified at design time during specify) but the JSON entry is missing this field.
3. Bump the file's top-level `last_updated` to today's date.
4. Extend the top-level `updated_by` string to include this mission: `"... + agent-prompt-deploy-pipeline-01KTMDDD (#567)"`.

**Files**:
- `docs/design/architecture/data/service-inventory.json`

**Validation**: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0 (valid JSON). The new entry follows the same key set as `felix-doc-auditor`'s entry.

### T012 — Update `signal-to-doc-map.json`

**Purpose**: Add a `change_class` entry that tells the doc-auditor which surfaces are affected when an agent prompt file changes.

**Steps**:

1. Open `docs/design/architecture/data/signal-to-doc-map.json` and find the existing entries to see the schema. Each entry typically has `match`, `change_class`, and `doc_targets` fields.
2. Add a new entry with:
   - `match`: `{"source": "merge-to-main", "path_pattern": "scripts/openclaw/agents/*/AGENTS.md"}` (or whatever the existing matchers look like; align style)
   - `change_class`: `"agent-prompt-changed"`
   - `doc_targets`: list of doc paths affected — at minimum, the affected agent's entry in `service-inventory.json` and the agent-prompt-sync entry, plus `service-inventory.md` and `agent-prompt-sync-ops.md` if relevant
3. If the existing schema doesn't accept this shape exactly, adapt to the actual schema (do not invent a new structure).

**Files**:
- `docs/design/architecture/data/signal-to-doc-map.json`

**Validation**: JSON parses cleanly; entry follows the same structure as siblings.

### T013 — Update `service-inventory.md` narrative

**Purpose**: Add a narrative section describing the new deploy pipeline, the slug→deploy-dir mapping rule (currently buried in memory), and the manual install procedure.

**Steps**:

1. Open `docs/design/architecture/service-inventory.md`. Find the right location for a new section — likely under an "office2 services" or "deployment helpers" parent section.
2. Add a section titled `## Agent Prompt Deploy Pipeline` with subsections:
   - **Purpose** — one paragraph summarizing what the pipeline does
   - **Architecture** — the office2-pull design (timer + git pull --ff-only + atomic file copy)
   - **Slug → deploy-dir mapping** — the rule that agent slug ≠ deploy dir, with the explicit table (felix-admin-capture → inbox-agent, etc.) and a pointer to `service-inventory.json` as the source of truth
   - **Files synced** — the in-scope filename allowlist; the exclusion list (HEARTBEAT.md, *.tmpl, *.bak*, GOVERNANCE.md)
   - **Operator surface** — reference the agent-prompt-sync-ops.md runbook (T015) and the manual install procedure
3. Keep the section focused; this is reference narrative, not a how-to. The runbook is the how-to.

**Files**:
- `docs/design/architecture/service-inventory.md`

**Validation**: Section reads cleanly; cross-references resolve; existing content is untouched.

### T014 — Update `openclaw-agent-setup.md` runbook

**Purpose**: Update the existing openclaw-agent-setup runbook to mention the new deploy pipeline; clarify that subsequent prompt edits no longer require a manual file copy after the one-time unit install.

**Steps**:

1. Open `docs/runbooks/openclaw-agent-setup.md`. Locate the section about deploying agent prompt files (likely under "Deploying a new agent" or similar).
2. Add a new sub-section titled "Deploy pipeline (post-2026-06-08)" that:
   - States the pipeline auto-syncs `AGENTS.md` + other in-scope files from `scripts/openclaw/agents/<slug>/` to `/data/services/openclaw/<deploy-dir>/` every 5 minutes
   - References the new agent-prompt-sync-ops.md runbook for install + verification
   - Notes that the existing manual `scp`/`cat` deploy steps are now FALLBACK ONLY — used when the helper is broken or being bootstrapped
3. Do NOT delete the manual instructions — keep them as the rollback / bootstrap path.

**Files**:
- `docs/runbooks/openclaw-agent-setup.md`

**Validation**: Section reads cleanly; cross-references resolve; existing manual instructions still present as fallback.

### T015 — Create `agent-prompt-sync-ops.md` runbook

**Purpose**: New operator-facing runbook with install + verify + troubleshoot + rollback. Lift content from `quickstart.md` (Phase 1 artifact, already drafted).

**Steps**:

1. Create `docs/runbooks/agent-prompt-sync-ops.md` with the kg-automation runbook frontmatter convention:
   ```yaml
   ---
   id: agent-prompt-sync-ops
   doc_type: runbook
   title: Agent prompt sync — operator runbook
   status: active
   level: operator
   owners: ["kgale"]
   last_validated: 2026-06-08
   version: 1.0
   ---
   ```
2. Lift content from `kitty-specs/agent-prompt-deploy-pipeline-01KTMDDD/quickstart.md` covering:
   - First-time install (one-time, post-merge) — full bash block
   - First-tick verification (within 5 minutes)
   - Spot-check that prompts actually landed (MD5 comparison)
   - Manual trigger
   - Dry-run
   - Single-agent force-sync
   - Troubleshooting (5+ scenarios)
   - Rollback (revert + helper-broken paths)
   - Observability table
3. Adapt the quickstart language to runbook style: more declarative, less narrative; use imperative section headings ("Install", "Verify", "Troubleshoot", "Rollback") and active voice.
4. Make sure the runbook is independently usable — an operator should not need to consult the mission's kitty-specs to follow this runbook.

**Files**:
- `docs/runbooks/agent-prompt-sync-ops.md` (new)

**Validation**: Frontmatter parses; runbook is structurally complete; an operator who has never seen this codebase can follow it end-to-end.

## Definition of Done

- [ ] All 5 files updated/created
- [ ] `service-inventory.json` parses cleanly + new entry matches existing-entry schema
- [ ] `signal-to-doc-map.json` parses cleanly + new entry matches existing schema
- [ ] `service-inventory.md` has the new section + cross-references the runbook + lists the slug→deploy-dir mapping explicitly
- [ ] `openclaw-agent-setup.md` mentions the pipeline + retains manual fallback
- [ ] `agent-prompt-sync-ops.md` exists with the runbook frontmatter + all sections per the subtask guidance
- [ ] `python3 tooling/scripts/validate_docs.py` exits 0 (the project's existing doc validator)
- [ ] Lane committed; WP frontmatter `lane` updated to `for_review`

## Risks

- `validate_docs.py` may reject the new runbook if frontmatter conventions have evolved. Mitigation: match the frontmatter of a recent runbook (e.g., `docs/runbooks/doc-auditor-driver-ops.md`) exactly.
- `service-inventory.json` is a richly-typed schema; adding malformed entries fails CI. Mitigation: copy structure from `felix-doc-auditor` (the most similar existing entry) and adapt only the necessary fields.
- The narrative in `service-inventory.md` could drift from the JSON. Mitigation: the JSON is canonical (per Felix Constitution Directive 5); the narrative summarizes. If they conflict, the JSON wins.

## Reviewer Guidance

- Verify `service-inventory.json` parses (`python3 -c "import json; json.load(open(...))"`)
- Verify the new agent-prompt-sync service entry has the same key set (or a superset) as `felix-doc-auditor`'s entry
- Verify `main.source_in_repo` is now populated
- Verify the runbook contains the CORRECT `-m` invocation form (`python3 -m scripts.openclaw.deploy.deploy_agent_prompts`, not the script-path form)
- Verify the slug→deploy-dir table in service-inventory.md matches the actual mappings (consult service-inventory.json)
- Verify no broken cross-references between updated docs

## Next Step

After this WP merges to coordination branch:
- `spec-kitty accept --mission agent-prompt-deploy-pipeline-01KTMDDD`
- `spec-kitty merge --mission agent-prompt-deploy-pipeline-01KTMDDD`
- Post-merge: operator runs the install procedure from agent-prompt-sync-ops.md

## Activity Log

- 2026-06-08T21:24:58Z – claude – shell_pid=983 – Assigned agent via action command
- 2026-06-08T21:29:34Z – claude – shell_pid=983 – All 5 doc surfaces updated; JSONs validate.
- 2026-06-08T21:29:38Z – claude – shell_pid=2781 – Started review via action command

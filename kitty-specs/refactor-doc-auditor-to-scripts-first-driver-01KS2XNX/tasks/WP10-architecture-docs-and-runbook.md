---
work_package_id: WP10
title: Architecture docs and operator runbook
dependencies:
- WP09
requirement_refs:
- FR-012
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T046
- T047
- T048
- T049
- T050
- T051
phase: Phase 6 — Final docs
assignee: ''
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "44410"
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/runbooks/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/felix-d6-survey.md
- docs/runbooks/doc-auditor-driver-ops.md
tags: []
---

# Work Package Prompt: WP10 — Architecture docs and operator runbook

## Objective

Update the architecture JSON sources, append a context note to the d6-survey doc, write the new operator runbook, and refresh the memory file. Closes spec FR-012 + FR-013 + C-008.

This WP runs after WP09 because it needs the final operational state to be live and verified.

## Context

- The architecture JSONs (`service-inventory.json`, `data-flows.json`, `credential-manifest.json`) are authoritative per Felix Constitution Directive 5. Markdown views must match.
- `felix-d6-survey.md`'s prior "LOW PRIORITY" verdict for felix-doc-auditor was about further helper-extraction. #343 changed the orchestration layer above the helpers. Adding a note prevents future readers from misinterpreting the survey's verdict.
- The new runbook at `docs/runbooks/doc-auditor-driver-ops.md` becomes the operator's authoritative reference, replacing the conceptual coverage in the old AGENTS.md + SKILL.md (which are deleted at cutover).
- Memory file update keeps Claude (this AI) able to recall the post-rework ops model.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP10 --agent <name>`.

## Subtasks

### T046 — Update `service-inventory.json` — felix-doc-auditor entry

**Purpose**: Reflect the new invocation surface in the authoritative service registry.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`.

2. Update the `felix-doc-auditor` entry's fields:
   - `name`: Optionally rename to `felix-doc-auditor-driver` OR keep `felix-doc-auditor` for continuity (recommendation: keep — the SERVICE is still felix-doc-auditor; only the implementation changed)
   - `exec_start`: change from `openclaw agent --agent felix-doc-auditor --message 'Cron tick…' --timeout 1500` to `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py`
   - `session_mode`: change from `isolated` (openclaw concept) to `stateless` (new field value; document in field-key glossary)
   - `model`: keep `anthropic/claude-haiku-4-5`
   - `dependencies`: update list
     - Remove: openclaw-gateway:18789 (driver doesn't go through openclaw)
     - Keep: gh-cli, doc-domain-map.json
     - Replace: "doc-audit" SKILL.md → reference to `scripts/doc_audit/prompts/` directory
     - Add: anthropic-api-key (file at `/data/services/openclaw/secrets/anthropic`)
     - Add: signal-to-doc-map.json
     - Add: drift-events.jsonl
   - `config_files`: update list
     - Remove: `/data/services/openclaw/felix-doc-auditor/AGENTS.md` (deleted at cutover)
     - Remove: `~/.openclaw/skills/doc-audit/SKILL.md` (no longer loaded at runtime — kept for historical reference but not used)
     - Add: `~/.config/systemd/user/felix-doc-auditor.service` (already there; verify)
     - Add: `scripts/doc_audit/config.toml`
     - Add: `scripts/doc_audit/prompts/*.prompt.md`
   - `health_check`: update
     - From `logs` at activity log path
     - To `last-tick.json` at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`
     - Expected: `status: "success" within last 2 hours`
   - `updated_by`: set to `#343`
   - `last_updated`: today's date

3. The top-level `last_updated` field in service-inventory.json: set to today.

**Files**:
- Modified: `docs/design/architecture/data/service-inventory.json`

**Validation**:
- [ ] JSON parses
- [ ] All fields above updated
- [ ] `updated_by: #343` and `last_updated: <today>` set on entry + top-level

---

### T047 — Update `data-flows.json`

**Purpose**: Remove openclaw-session-state edges; add direct-API edges.

**Steps**:

1. Open `docs/design/architecture/data/data-flows.json`.

2. Locate the doc-audit-related data flow entries (if any).

3. Remove edges that referenced openclaw session state:
   - "felix-doc-auditor → openclaw session jsonl" edges
   - Any reference to openclaw-agent's per-tick session

4. Add edges for the new driver:
   - `felix-doc-auditor-driver → anthropic API (direct HTTPS)` — flow name: `direct-claude-api`
   - `felix-doc-auditor-driver → /data/services/openclaw/felix-doc-auditor-driver/last-tick.json` — flow name: `tick-signal-write`
   - `felix-doc-auditor-driver ← /data/services/security-monitor/logs/drift-events.jsonl` (read) — existing flow if present, otherwise add
   - `felix-doc-auditor-driver ← /data/services/openclaw/secrets/anthropic` (read) — sensitive flow, do NOT include the file contents

5. Set `updated_by: #343` and bump `last_updated`.

**Files**:
- Modified: `docs/design/architecture/data/data-flows.json`

**Validation**:
- [ ] JSON parses
- [ ] No remaining references to openclaw-session-state for felix-doc-auditor
- [ ] New direct-API edge documented
- [ ] tick-signal-write edge documented

---

### T048 — Update `credential-manifest.json`

**Purpose**: Note the Anthropic key is now used by the driver process directly, not via openclaw.

**Steps**:

1. Open `docs/design/architecture/data/credential-manifest.json`.

2. Find the `anthropic` credential entry.

3. Update the `used_by` list:
   - From: `["openclaw-gateway"]`
   - To: `["openclaw-gateway", "felix-doc-auditor-driver"]`

4. Update the `notes` field to note both consumers (openclaw-gateway for other agents that still use openclaw; felix-doc-auditor-driver via direct file read).

5. Verify the `storage` field still accurately describes the locations.

6. Set top-level `updated_by: #343` and `last_updated: <today>`.

**Files**:
- Modified: `docs/design/architecture/data/credential-manifest.json`

**Validation**:
- [ ] JSON parses
- [ ] `used_by` lists both consumers
- [ ] Notes accurately describe the dual consumption pattern

---

### T049 — Append note to `felix-d6-survey.md`

**Purpose**: Document the relationship between the prior survey's verdict and this mission's outcome.

**Steps**:

1. Open `docs/design/architecture/felix-d6-survey.md`.

2. Find the section discussing `felix-doc-auditor` (search for "felix-doc-auditor — 485L"). The prior verdict was "LOW PRIORITY".

3. Append a "## Update — 2026-05-20 — #343" subsection or callout box (don't modify the original prose):

   ```markdown
   ---

   ## Update — 2026-05-20 — issue #343

   The "LOW PRIORITY" verdict for `felix-doc-auditor` above assessed
   further **helper-extraction** opportunities (extracting more of the prose
   procedure into Python helpers like `handle_audit_routing.py` and
   `handle_drift_events.py`). That verdict remains correct for that
   question — the high-value extractions have already happened.

   **#343 changed a different dimension**: the orchestration layer
   **above** the helpers. The agent's role of interpreting a 38 KB
   SKILL.md procedure as runtime LLM prose was its own cost-and-reliability
   problem, separate from helper extraction. Mission #343 replaces the
   agent-as-orchestrator with a Python driver that calls the existing
   helpers + makes narrow LLM judgment calls.

   Net effect: this survey's "low priority" verdict no longer applies as
   an overall judgment of felix-doc-auditor's optimization opportunity.
   The helper-extraction surface IS low priority; the orchestrator surface
   was high priority and was addressed by #343.

   See: kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
   ```

4. Bump the doc's `last_validated` frontmatter field (if present) to today's date.

**Files**:
- Modified: `docs/design/architecture/felix-d6-survey.md`

**Validation**:
- [ ] Note appended without modifying the original verdict prose
- [ ] Cross-reference to this mission is present
- [ ] Frontmatter date updated

---

### T050 — Write `docs/runbooks/doc-auditor-driver-ops.md`

**Purpose**: The new authoritative operator runbook (FR-013).

**Steps**:

1. Create `docs/runbooks/doc-auditor-driver-ops.md`. Use the existing runbook conventions (frontmatter, headers, command examples).

2. Structure:

   ```markdown
   ---
   title: felix-doc-auditor driver operations
   doc_type: runbook
   audience: operator
   created: 2026-MM-DD
   last_validated: 2026-MM-DD
   ---

   # felix-doc-auditor driver — operations runbook

   ## Overview
   <link to mission #343 + spec; one-paragraph what-it-does>

   ## Architecture
   <link to plan.md project structure diagram + brief description>

   ## Health checks
   ### 30-second check
   <commands from quickstart.md "Health check (30 seconds)" section>

   ### Forcing a manual tick
   <commands from quickstart.md>

   ### Dry-run preview
   <commands from quickstart.md>

   ### Inspecting recent tick history (journal grep for SUMMARY:)
   <commands from quickstart.md>

   ## Configuration
   ### Default location
   ### Override path

   ## Prompt artifact inspection
   <quickstart.md "Reading the prompt artifacts" section>

   ## Backlog recovery
   <quickstart.md "Backlog recovery" section>

   ## Stuck lock recovery
   <quickstart.md "Stuck status:in-progress lock recovery" section>

   ## Pending-approval workflow
   <quickstart.md "Pending-approval workflow" section + actor-verification reminder>

   ## Cost / token usage
   <quickstart.md "Cost / token usage" section + link to baseline files>

   ## Troubleshooting

   ### Tick failure
   ### Stale signal
   ### Cost spike
   ### API outage

   ## Re-baselining (annual cadence)
   <pointer to baselines/ directory + measure-tokens.py>

   ## What changed vs the old openclaw-agent auditor
   <quickstart.md "What changed" table>

   ## Cross-references
   <links to spec.md, plan.md, contracts/, baselines/>
   ```

3. Heavy lift can borrow from `quickstart.md` content; the runbook is the production-version + slightly more detail on troubleshooting.

4. Add a one-line entry in `docs/INDEX.md` pointing to this new runbook (or capture as docs-debt issue if INDEX update is out-of-scope per repo conventions).

**Files**:
- New: `docs/runbooks/doc-auditor-driver-ops.md` (~400 lines)
- Optionally modified: `docs/INDEX.md` (or filed as docs-debt issue)

**Validation**:
- [ ] Runbook covers every quickstart.md section + adds troubleshooting depth
- [ ] All command examples are tested (operator can copy-paste)
- [ ] Cross-references are correct
- [ ] Discovery: link from INDEX.md OR debt issue filed

---

### T051 [P] — Update memory file `reference_felix_doc_auditor_ops.md`

**Purpose**: Refresh Claude's persistent memory about felix-doc-auditor's ops model.

**Steps**:

1. Open `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/reference_felix_doc_auditor_ops.md`.

2. Replace the old content (which described the openclaw-agent ops model) with content reflecting the new driver model. Use the template at the top of this file.

3. Key changes:
   - Schedule: still systemd user timer hourly — unchanged
   - Locations: driver at `/home/claude/kg-automation/scripts/doc_audit/run.py`; tick signal at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`
   - Activity log: same location, same format
   - Quick-reference commands: from `quickstart.md`
   - Concurrency: in-band via `status:in-progress` GitHub label lock (unchanged); plus the structured tick signal as a new observation surface
   - Authoritative architecture: see `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/` for design; this memory file links to it
   - Identity: still `kg-felix-bot`

4. Bump description field to reflect the rewrite + add a `last_updated` field with today's date.

5. Update the index entry in MEMORY.md if the description changes substantively.

**Files**:
- Modified: `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/reference_felix_doc_auditor_ops.md`
- Possibly modified: `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/MEMORY.md` (index entry tweak)

**Note on ownership**: Memory files live OUTSIDE the repo (in `~/.claude/...`). They're not in `owned_files`. The WP09 reviewer should verify the update via cross-referencing during review.

**Validation**:
- [ ] Memory file reflects new ops model
- [ ] Cross-reference to this mission included
- [ ] MEMORY.md index entry updated if needed

---

## Definition of Done

- [ ] service-inventory.json reflects new invocation, new dependencies, new health-check
- [ ] data-flows.json removes openclaw-session edges, adds direct-API edges
- [ ] credential-manifest.json updates Anthropic key's `used_by`
- [ ] felix-d6-survey.md appended with the #343 context note (no rewrite of prior verdict)
- [ ] docs/runbooks/doc-auditor-driver-ops.md written; covers every operator surface
- [ ] Memory file updated
- [ ] All architecture JSONs have `updated_by: #343` set on touched entries

## Risks

| Risk | Mitigation |
|---|---|
| JSON edits introduce syntax errors | Run `python3 -m json.tool` after each edit; CI's `validate_docs.py` is the safety net |
| Doc references go stale before final merge | Spot-check after the last commit; manually verify cross-references |
| Memory file update inconsistent with the runbook | Use the runbook as the source of truth; memory file summarizes |

## Reviewer Guidance

- Verify `updated_by: #343` set on every modified JSON entry
- Confirm markdown views match the JSON sources (CLAUDE.md "Documentation Standards" principle)
- Spot-check runbook commands by running them manually against office2 to confirm they work
- Confirm the d6-survey appended note preserves the original verdict prose

## Implementation Command

```bash
spec-kitty agent action implement WP10 --agent <name>
```

## Cross-references

- **Spec**: FR-012 (architecture doc updates), FR-013 (operator quick-reference)
- **Research**: D11 (operator quick-reference scope)
- **Quickstart**: `quickstart.md` (source material for the runbook)
- **Predecessors**: WP07 (baselines/), WP09 (cutover-log.md) — runbook references both

## Activity Log

- 2026-05-21T14:43:34Z – claude:opus-4.7:implementer:implementer – shell_pid=34158 – Started implementation via action command
- 2026-05-21T14:51:18Z – claude:opus-4.7:implementer:implementer – shell_pid=34158 – Final WP — docs ready: 3 architecture JSONs (service-inventory, data-flows, credential-manifest) updated with updated_by: #343; felix-d6-survey.md appended with #343 context note (original verdict preserved); new docs/runbooks/doc-auditor-driver-ops.md (492 lines, 13 sections); INDEX.md updated; memory file rewritten for post-#343 ops model.
- 2026-05-21T14:52:24Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=36057 – Started review via action command
- 2026-05-21T14:55:42Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=36057 – Moved to planned
- 2026-05-21T14:55:47Z – claude:opus-4.7:implementer:implementer – shell_pid=37078 – Started implementation via action command
- 2026-05-21T15:00:31Z – claude:opus-4.7:implementer:implementer – shell_pid=37078 – Cycle 2: 3 findings fixed
- 2026-05-21T15:01:08Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=38260 – Started review via action command
- 2026-05-21T15:05:53Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=38260 – Review changes requested
- 2026-05-21T15:07:25Z – claude:opus-4.7:implementer:implementer – shell_pid=40104 – Started implementation via action command
- 2026-05-21T15:10:58Z – claude:opus-4.7:implementer:implementer – shell_pid=40104 – Cycle 3: markdown views consistent with JSON sources
- 2026-05-21T15:11:44Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=40983 – Started review via action command
- 2026-05-21T15:18:29Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=40983 – Moved to planned
- 2026-05-21T15:21:03Z – claude:opus-4.7:implementer:implementer – shell_pid=43493 – Started implementation via action command
- 2026-05-21T15:25:10Z – claude:opus-4.7:implementer:implementer – shell_pid=43493 – Cycle 4: data-flows views (md, view.md, mmd) updated to match JSON
- 2026-05-21T15:25:48Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=44410 – Started review via action command

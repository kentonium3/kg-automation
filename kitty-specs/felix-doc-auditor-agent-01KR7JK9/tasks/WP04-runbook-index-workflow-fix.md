---
work_package_id: WP04
title: Ops runbook + INDEX + weekly workflow fix
dependencies: []
requirement_refs:
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Worktree allocated by lanes.json after finalize-tasks. Branch from main.
subtasks:
- T014
- T015
- T016
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: docs/runbooks/
execution_mode: code_change
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- docs/runbooks/doc-auditor-ops.md
- docs/INDEX.md
- .github/workflows/doc-audit-weekly.yml
tags: []
---

# WP04 — Ops runbook + INDEX + weekly workflow fix

## Objective

Three deliverables that don't fit elsewhere but must ship in this mission: (1) the ops runbook for the new agent (FR-007), (2) the docs index update (per change-control protocol for new docs), and (3) the FR-008 fix to `doc-audit-weekly.yml` (silent-suppression bug currently masking 3 weeks of weekly audits).

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9`
- Spec: [../spec.md](../spec.md) — FR-007 (runbook + registration), FR-008 (weekly fix)
- Plan: [../plan.md](../plan.md)
- Research: [../research.md](../research.md) — R-012 (weekly fix details), R-014 (canary procedure — referenced by runbook)
- Quickstart: [../quickstart.md](../quickstart.md) — covers the operational procedures the runbook should encode

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: per-WP worktree from `lanes.json`. Branch from `main`. Merge back via spec-kitty review/merge.

## Subtasks

### T014 — Write docs/runbooks/doc-auditor-ops.md

**Purpose**: The operations runbook for `felix-doc-auditor`. ~250-350 lines.

**File**: `docs/runbooks/doc-auditor-ops.md` (new)

**Steps**:

1. Read existing runbook for reference style: `docs/runbooks/transcribe-ops.md` is a good model for structure (Service Overview → Service Management → Data → Updating → Troubleshooting).

2. Compose the runbook with these sections:

   **Front matter**:
   ```yaml
   ---
   title: Doc Auditor Operations Runbook
   doc_type: runbook
   audience: agents_and_humans
   status: draft
   last_updated: '2026-05-09'
   ---
   ```

   **Service Overview** (~20 lines):
   - Agent name, current autonomy level, model, schedule, host
   - Workspace path, skill path, log path
   - Source-of-truth: this repo's `scripts/openclaw/agents/felix-doc-auditor/` and `scripts/openclaw/skills/doc-audit/`
   - Cross-reference: AGENT-REGISTRY.md, service-inventory.md sections

   **How It Operates** (~30 lines):
   - Cron fires every 60 min
   - Queries open audit issues lacking `status:in-progress` label
   - Picks oldest, claims with label
   - Loads doc-audit skill
   - Per-doc analysis → classify → propose
   - Level 1: WhatsApp summary + reply
   - Commit + file debt issues + summary + close
   - Release label
   - (Reference the lifecycle diagram in `kitty-specs/.../data-model.md`)

   **Manual Trigger** (~15 lines):
   - Use case: ad-hoc audit against a specific issue
   - Command: `openclaw delegate felix-doc-auditor "Process audit issue #<N>"`
   - Same agent invocation; no different code path

   **Adding a Document to the Audit Scope** (~20 lines):
   - Edit `docs/design/architecture/data/doc-domain-map.json`
   - Add the doc path to the appropriate `area/*` array
   - Bump `last_updated` and `updated_by`
   - On the next audit (per-merge or weekly) the doc is included

   **Adjusting the Confidence Threshold** (~15 lines):
   - The threshold rules live in `scripts/openclaw/skills/doc-audit/SKILL.md`
   - To make the agent more conservative: add edit categories to the "NOT high confidence" list
   - To make it more aggressive: add categories to the high-confidence list (only with strong evidence)
   - Push the skill update; office2 picks up via git pull (or re-deploy via `scripts/office2/deploy/felix-doc-auditor.sh` from WP05)
   - Activate by reload (no service restart needed; agent loads skill at start of every audit)

   **Stale-Lock Recovery** (~15 lines):
   - Symptom: an audit issue carries `status:in-progress` for >30 minutes
   - Cause: agent crashed or WhatsApp delivery failed at Level 1
   - Recovery: `gh issue edit <#> --remove-label "status:in-progress" --repo kentonium3/kg-automation`
   - The next cron tick will re-pick up the issue
   - If recurring, check the activity log for error patterns

   **Kill Switch** (~15 lines):
   - To temporarily disable the agent:
     - Edit `/home/claude/.openclaw/openclaw.json`; set the cron entry's `enabled: false` (or comment out per existing convention)
     - Restart OpenClaw cron service
   - To re-enable: reverse the edit + restart

   **Promotion to Supervised (Level 2)** (~20 lines):
   - Process: separate governance decision after ~1 week clean operation
   - Evidence required (per Felix Constitution autonomy promotion):
     - Audit issues processed without false-positive edits
     - WhatsApp approval cycle worked smoothly (no recurring `reject` for legitimate proposals)
     - No edits to constitution / CLAUDE.md / credentials
     - Audit trail intact
   - Operational change: agent reads the new level from `agent-registry.json` at start of next audit; skips WhatsApp step for Level 2
   - Update locations: AGENT-REGISTRY.md (new transition row + autonomy field), agent-registry.json (autonomy_level + transition_history)

   **Troubleshooting** (~30 lines, table format):

   | Symptom | Likely cause | Fix |
   |---|---|---|
   | Agent never processes audit issues | Cron not enabled | Check openclaw.json cron entry; restart OpenClaw cron |
   | Issue stuck at status:in-progress | Agent crashed mid-run | Stale-lock recovery (above) |
   | Agent files debt issues for high-confidence types | Skill threshold misconfigured | Review SKILL.md confidence rules; adjust |
   | Agent commits wrong content | Comparison rules wrong or system-state source out of date | Revert commit; investigate skill comparison rules; consider lowering autonomy |
   | WhatsApp delivery fails | Existing WhatsApp issue (see whatsapp-ops.md) | Per `docs/runbooks/whatsapp-ops.md` |
   | GitHub API rate limit hit | Many audits stacked + many commits/issues per audit | Lower polling cadence in openclaw.json |
   | Agent reads file outside scope | Skill or AGENTS.md mistake | Inspect agent activity log; tighten TOOLS.md disallowed list |

   **Security Baseline Reset** (~15 lines):
   - After deploying the agent, the security monitoring baselines on office2 should be updated:
     - New deployed_by field in service-inventory.json
     - New `/data/services/openclaw/felix-doc-auditor/` directory
     - New skill at `~/.openclaw/skills/doc-audit/` (if deployed there)
   - Reset procedure (per existing pattern in transcribe-ops.md): `cd /data/services/security-monitor && ./scripts/generate-baselines.sh`

**Validation**:
- [ ] All 9 sections present
- [ ] Cross-references to AGENTS.md, SKILL.md, AGENT-REGISTRY.md, agent-registry.json, doc-domain-map.json, openclaw.json all resolve
- [ ] Troubleshooting table covers ≥6 symptoms
- [ ] Stale-lock recovery section is unambiguous (Kent or claude can run the gh command without referring to other docs)

---

### T015 — Update docs/INDEX.md

**Purpose**: Per the change-control protocol, every new doc under `docs/` requires an INDEX update. The new runbook needs an entry. ~3-5 lines added.

**File**: `docs/INDEX.md` (modify)

**Steps**:

1. Read the existing INDEX. Find the runbooks section.

2. Add an entry for the new runbook in alphabetical position:
   ```markdown
   - [doc-auditor-ops.md](runbooks/doc-auditor-ops.md) — felix-doc-auditor agent operations: how it runs, manual triggers, scope management, stale-lock recovery, kill switch
   ```

3. If INDEX uses a Divio classification, mark this as a runbook (operational guide).

**Validation**:
- [ ] New entry in correct alphabetical position
- [ ] Description matches the runbook's content scope (one-line)
- [ ] Link resolves to the actual file path

---

### T016 — Modify .github/workflows/doc-audit-weekly.yml per R-012

**Purpose**: Fix the silent-suppression bug per FR-008. ~5-line YAML change.

**File**: `.github/workflows/doc-audit-weekly.yml` (modify)

**Steps**:

1. Read the current file. Locate the "Check for existing weekly audit" step (around line 18-30).

2. Apply the change per R-012:

   **Before**:
   ```yaml
   - name: Check for existing weekly audit
     id: existing
     env:
       GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
     run: |
       COUNT=$(gh issue list --label "P2-debt" --state open \
         --search "Weekly doc audit" --json number --jq 'length')
       if [ "$COUNT" -gt "0" ]; then
         echo "skip=true" >> "$GITHUB_OUTPUT"
         echo "Open weekly audit issue already exists — skipping"
       else
         echo "skip=false" >> "$GITHUB_OUTPUT"
       fi
   ```

   **After**:
   ```yaml
   - name: Check for existing weekly audit (current week only)
     id: existing
     env:
       GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
     run: |
       DATE=$(date +%Y-%m-%d)
       COUNT=$(gh issue list --label "P2-debt" --state open \
         --search "Weekly doc audit — ${DATE} in:title" --json number --jq 'length')
       if [ "$COUNT" -gt "0" ]; then
         echo "skip=true" >> "$GITHUB_OUTPUT"
         echo "Open weekly audit issue already exists for ${DATE} — skipping"
       else
         echo "skip=false" >> "$GITHUB_OUTPUT"
       fi
   ```

3. The change adds the `${DATE}` variable and the `in:title` qualifier to the search. Step name updated for clarity. Skip log message includes the date for traceability.

4. After committing, manually trigger the workflow once to verify it works: `gh workflow run doc-audit-weekly.yml`. The workflow should create a new weekly audit issue (since none for today exists) regardless of #186 still being open.

**Validation**:
- [ ] YAML still parses (workflow file syntax)
- [ ] Step renamed for clarity
- [ ] Search uses `in:title` qualifier scoped to current `${DATE}`
- [ ] Manual workflow run creates a new issue (proves the fix lives — verify after merge)

## Definition of Done (WP04)

- [ ] All 3 files modified/created per their per-subtask validation
- [ ] `docs/runbooks/doc-auditor-ops.md` is comprehensive (9 sections, ~300 lines)
- [ ] `docs/INDEX.md` has the new runbook entry in alphabetical position
- [ ] `.github/workflows/doc-audit-weekly.yml` updated per R-012
- [ ] After merge, manual `gh workflow run doc-audit-weekly.yml` succeeds and creates a new weekly issue

## Risks

- **YAML indentation matters** — heredoc-style sections in GitHub Actions are sensitive. Validate the file with `yamllint` or a YAML parser before commit.
- **Runbook becomes stale immediately** — the runbook references the agent's behavior. If WP01/WP02 deviate from spec during implementation, the runbook needs updating too. Cross-check after WP01/WP02 land.
- **Workflow change has no automated test** — validation requires a manual `gh workflow run` after merge. Add to mission close-out checklist.

## Reviewer guidance

A reviewer should check:
1. Runbook covers all FR-007 topics (operate, manual trigger, domain map, threshold tuning, troubleshooting, kill switch, stale-lock)
2. Runbook style matches `transcribe-ops.md` (Service Overview, sections, troubleshooting table format)
3. INDEX update is in alphabetical position
4. YAML change is exactly per R-012; no other workflow logic touched
5. After merge, suggest verifying the YAML fix works by triggering the workflow manually

## Implementation command

```bash
spec-kitty agent action implement WP04 --agent <agent-name>
```

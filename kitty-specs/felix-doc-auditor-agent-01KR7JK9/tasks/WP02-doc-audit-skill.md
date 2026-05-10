---
work_package_id: WP02
title: doc-audit skill
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
agent: "codex:gpt5:reviewer:reviewer"
shell_pid: "40706"
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: scripts/openclaw/skills/doc-audit/
execution_mode: code_change
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- scripts/openclaw/skills/doc-audit/**
tags: []
---

# WP02 — doc-audit skill

## Objective

Create `scripts/openclaw/skills/doc-audit/SKILL.md` per FR-006 and R-013. The skill must be self-contained — `felix-doc-auditor` can run a complete audit using only this skill plus the domain map, with no implicit knowledge.

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9`
- Spec: [../spec.md](../spec.md) — FR-001 through FR-005 are the workflow this skill encodes; FR-006 is the skill itself
- Plan: [../plan.md](../plan.md)
- Research: [../research.md](../research.md) — R-013 (skill scope and structure), R-006 (debt template), R-009 (concurrency label)
- Contracts: [../contracts/](../contracts/) — `commit-message.template.md`, `audit-summary-comment.template.md`
- Conventions reference: `scripts/openclaw/skills/skill-author/SKILL.md` is the authoritative format guide; `scripts/openclaw/skills/vikunja-api/SKILL.md` and `scripts/openclaw/skills/escalation/SKILL.md` are good examples to model.

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: per-WP worktree from `lanes.json`. Branch from `main`. Merge back via spec-kitty review/merge.

## Subtasks

### T006 — Write SKILL.md

**Purpose**: The full skill document. Must encode every rule the agent needs to run an audit. ~150-200 lines.

**File**: `scripts/openclaw/skills/doc-audit/SKILL.md` (new)

**Steps**:

1. **Read** `scripts/openclaw/skills/skill-author/SKILL.md` first. This is the authoritative format guide. Follow its conventions exactly.

2. **Front matter** (top of file):
   ```yaml
   ---
   name: doc-audit
   description: >-
     How felix-doc-auditor reads and acts on Doc Audit and Weekly Doc Audit
     GitHub issues. Defines the audit workflow, the high-confidence vs
     judgment threshold, the docs-debt issue template, the commit format,
     and error handling.
     Does NOT handle: agent identity (IDENTITY.md), agent standing orders
     (AGENTS.md), or runtime orchestration.
   version: 1.0.0
   ---
   ```

3. **`## What This Skill Is`** (one paragraph): name the purpose and the agents that consume it.

4. **`## Inputs`**: enumerate everything the agent feeds into a skill invocation:
   - Audit issue number (e.g., `186`)
   - Authoritative paths it depends on:
     - `docs/design/architecture/data/doc-domain-map.json` (scope contract)
     - System state sources (per `TOOLS.md` of the agent)

5. **`## Workflow`** (the core section, step-by-step):
   - Step 1: read audit issue body + labels + (if per-merge audit) the triggering commit SHA
   - Step 2: determine in-scope docs from `area/*` labels → domain map; if no labels, full-scope
   - Step 3: for each in-scope doc, read it and compare against current system state
   - Step 4: classify findings into: high-confidence edit, judgment gap, missing artifact, no change
   - Step 5: detect missing artifacts (deployed agents/services without docs)
   - Step 6: at Level 1, propose via WhatsApp; at Level 2, proceed to commit
   - Step 7: commit approved high-confidence edits atomically
   - Step 8: file docs-debt issues for judgment gaps and missing artifacts
   - Step 9: post summary comment + close audit issue
   - Step 10: log activity

6. **`## Confidence Threshold Rules`** (the heart of the skill — be exhaustive):

   **High-confidence edits** (commit directly after Level 1 approval):
   - Frontmatter `last_updated`, `last_validated`, `revision` field updates after a confirmed change
   - Service version numbers in `service-inventory.json` when the diff confirms an upgrade (cross-check the version against the running container if possible)
   - File paths after a confirmed rename (diff shows the move, the new path is unambiguous)
   - `updated_by` references for new entries (e.g., adding an issue/F-number)
   - Removing dead references after a file is deleted (diff shows the deletion)
   - Adding a new agent registry entry when the diff shows a new agent was deployed
   - Updating an agent's autonomy level when the diff has an explicit governance decision

   **NOT high confidence** (file as docs-debt instead):
   - Architectural description prose (any paragraph rewriting)
   - New runbook sections or procedures
   - Constitutional principle updates
   - Any change where the agent finds a discrepancy but cannot determine which source is authoritative
   - Any change that requires interpretation of intent (e.g., "should this be reflected here too?")

   **Constitutional guardrails** (NEVER edit autonomously, regardless of confidence):
   - `docs/constitution/FELIX-CONSTITUTION.md`
   - `CLAUDE.md` (any path)
   - Credential files (`.env`, `credentials.json`)
   - `kitty-specs/` and `.kittify/` (managed by spec-kitty)

7. **`## Comparison Rules`**: which system-state source to consult for which kind of doc:
   - Service-inventory docs (`service-inventory.json`/`.md`) → check `docker ps` (live containers), `service-inventory.json` itself
   - Hardware docs (`hardware-inventory.json`, `physical-topology.md`) → manual inspection or cross-reference to recent commits
   - Agent registry (`AGENT-REGISTRY.md`, `agent-registry.json`) → cross-reference each other (markdown is a view of JSON)
   - Network docs → `network-topology.json` is authoritative; `physical-topology.md` is a view
   - Runbooks → cross-reference with the deployed reality (the runbook should match what currently exists)

8. **`## Commit Format`**: cite `contracts/commit-message.template.md` and reproduce the format inline:
   ```
   chore(doc-audit): <one-line summary> (audit: #<N>)

   - <doc>: <change>
   - <doc>: <change>

   Refs #<audit-issue-number>.

   Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
   ```

9. **`## Docs-Debt Issue Template`**: cite `.github/ISSUE_TEMPLATE/docs-debt.md` and explain how to populate the six sections (Artifact, Gap description, Area, Cross-references, Draft outline, Success criteria). Emphasize that **Draft outline** is the load-bearing field.

10. **`## Error Handling`**:
    - Doc unreadable / locked: log to summary's "Items requiring human review"; skip; continue
    - Git push fails: pull --rebase; if conflict, abort the commits, demote to debt issues
    - GitHub API rate limit: exponential backoff; if persistent, leave audit at `status:in-progress` and exit
    - WhatsApp delivery fails (Level 1 only): do not proceed; leave audit at `status:in-progress`; log error
    - Domain map missing: critical; post a comment on the audit issue explaining; do not mutate anything

11. **`## Output Contracts`**: cross-reference `contracts/whatsapp-summary.template.md`, `contracts/whatsapp-reply-vocabulary.md`, `contracts/audit-summary-comment.template.md`, `contracts/agent-registry-entry.template.md`. State that these are the authoritative formats.

**Validation**:
- [ ] Front matter present and matches skill-author format
- [ ] All 11 sections present
- [ ] Confidence threshold rules enumerate 7+ high-confidence types AND 4+ "not high confidence" types AND 4 constitutional guardrails
- [ ] Workflow steps map 1:1 to the data-model lifecycle diagram
- [ ] Error handling covers ≥5 failure modes
- [ ] No reference to specific commits or issues that may not exist when the agent runs (use placeholders or `<sha>` notation)

---

### T007 — Add worked-examples section to SKILL.md

**Purpose**: Concrete examples of applying the confidence threshold to real recent commits. Trains the agent's intuition without requiring a separate examples file. ~30-50 lines (an `## Examples` section appended to SKILL.md).

**File**: same as T006 (append section)

**Steps**:

1. Pick 3-4 recent commits from `git log --oneline -20` that exercise different confidence categories.

2. For each, write a short example block:
   - **Example: frontmatter date update** (high confidence)
     - Commit: `<sha>` — `<subject>`
     - Triggers audit because: `<diff path matched <area>>`
     - Doc affected: `<doc path>`
     - Finding: doc's `last_updated` is older than the commit date
     - Classification: high confidence — `last_updated` field type is enumerated in confidence rules
     - Action: edit, commit with message format

   - **Example: missing runbook for new service** (judgment / missing artifact)
     - Commit: `<sha>` — added new service entry to `service-inventory.json`
     - Doc-debt: filed for missing runbook at `docs/runbooks/<service>-ops.md` because the service is deployed but undocumented
     - Draft outline in the debt issue: section headers (Service Overview, Health Check, Logs, Update Procedure, Troubleshooting, Backup)

   - **Example: prose rewrite needed** (judgment, NOT high confidence)
     - Commit: `<sha>` — added GPU acceleration to transcribe-api
     - Doc affected: `docs/runbooks/transcribe-ops.md`
     - Finding: "Updating the Docker Image" section needs new content for git-pull-based deploy
     - Classification: NOT high confidence (requires writing several paragraphs of new prose)
     - Action: file docs-debt issue with draft outline of the new section

3. Use real commits if possible; reference them by sha. If the commits are too recent / not yet propagated, use placeholder shas like `<sha-1>` and explain the example in abstract.

**Validation**:
- [ ] At least 3 examples covering: high-confidence frontmatter, missing-artifact, judgment prose
- [ ] Examples reference real commits or use clearly-marked placeholders

---

### T008 — Validate against skill-author conventions

**Purpose**: Final review pass to ensure the skill conforms to project standards. ~Validation only, may produce small fixes to T006/T007 output.

**Steps**:

1. Re-read `scripts/openclaw/skills/skill-author/SKILL.md` end-to-end.
2. For each requirement listed in the skill-author skill, check the doc-audit SKILL.md complies. Examples:
   - Front matter has `name`, `description`, `version`
   - `description` follows the 1-2 sentence + "Does NOT handle:" pattern
   - Sections use `##` Markdown
   - Code blocks use triple-backtick with language identifier where appropriate
3. Cross-reference an existing skill (e.g., `vikunja-api/SKILL.md`) for structural similarity.
4. If any conformance issues found, fix in SKILL.md.

**Validation**:
- [ ] Front matter complete
- [ ] Format matches skill-author conventions
- [ ] Compares structurally to at least one existing skill
- [ ] No conformance issues remaining

## Definition of Done (WP02)

- [ ] `scripts/openclaw/skills/doc-audit/SKILL.md` exists and contains all 11+ sections (10 from T006, 1 from T007)
- [ ] Skill passes the conformance check from T008
- [ ] Cross-references to contract files in `kitty-specs/.../contracts/` resolve to actual files
- [ ] Skill is internally complete: an unfamiliar agent can read SKILL.md alone (plus the domain map) and run a full audit

## Risks

- **Skill becomes too prescriptive** — over-specifying every edit type makes the skill brittle when new edit types appear. Mitigation: confidence rules are by category (frontmatter dates, version numbers, paths), not by specific files.
- **Skill too vague** — under-specifying produces inconsistent agent behavior. Mitigation: examples in T007 anchor the abstract rules.
- **Drift from contracts** — if the contracts in `kitty-specs/.../contracts/` change after this WP lands, the skill might fall out of date. The contracts are authoritative; the skill should reference them by path, not duplicate their full content.

## Reviewer guidance

A reviewer should check:
1. Confidence threshold rules cover the 7 high-confidence types from spec FR-002 verbatim
2. Workflow steps in section 5 match the lifecycle diagram in `data-model.md`
3. Examples in T007 are realistic and exercise different rule categories
4. Constitutional guardrails (no Constitution / CLAUDE.md / credentials / kitty-specs) are restated in the Confidence Threshold section

## Implementation command

```bash
spec-kitty agent action implement WP02 --agent <agent-name>
```

## Activity Log

- 2026-05-10T01:05:52Z – claude:sonnet:implementer:implementer – shell_pid=17245 – Started implementation via action command
- 2026-05-10T16:45:39Z – claude:sonnet:implementer:implementer – shell_pid=17245 – Ready for review: doc-audit skill created per FR-006/R-013, conforms to skill-author conventions. Orchestrator completed commit + status transitions on subagent's behalf (Bash permission denial on subagent).
- 2026-05-10T16:46:06Z – codex:gpt5:reviewer:reviewer – shell_pid=38608 – Started review via action command
- 2026-05-10T16:49:49Z – codex:gpt5:reviewer:reviewer – shell_pid=38608 – Rejected by codex (cycle 1/3, sandbox denied direct move-task; orchestrator recorded). Substantive finding: SKILL.md only triggers Level 1 WhatsApp approval for high-confidence edits but bypasses approval for debt-only audits and closure — violates FR-005 + FR-009 Assisted-level gating intent.
- 2026-05-10T16:50:03Z – claude:sonnet:implementer:implementer – shell_pid=39870 – Started implementation via action command
- 2026-05-10T16:53:02Z – claude:sonnet:implementer:implementer – shell_pid=39870 – Cycle 2: Fixed Level 1 approval gating per cycle-1 review feedback. Approval now triggers for any non-empty audit outcome.
- 2026-05-10T16:53:38Z – codex:gpt5:reviewer:reviewer – shell_pid=40706 – Started review via action command
- 2026-05-10T16:58:01Z – codex:gpt5:reviewer:reviewer – shell_pid=40706 – Review passed by codex (cycle 2/3, sandbox denied direct move-task; orchestrator recorded). Codex verdict: cycle-2 Level 1 gating fix covers non-empty audit outcomes, debt-only reply semantics, and empty-audit no-op contract. AGENTS.md cross-reference unaffected.

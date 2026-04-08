---
title: Runbook Audit Prompt — April 2026
doc_type: reference
status: approved
---

# Runbook & Governance Doc Audit — Cleanup Prompt

This file contains a complete inventory, assessment, and execution
instructions for cleaning up the docs/runbooks/ directory following
two major changes:

1. The shift from func-spec files to GitHub Issues as the feature
   planning record
2. The retirement of the old multi-platform / GitHub Actions runner
   / handoff JSON workflow

Read this entire file before executing anything. Execute each section
in order.

---

## Context

The kg-automation project has shifted:

**OLD workflow:**
- Features tracked in `docs/func-spec/F0NN_*.md` files
- GitHub Actions runner + Claude Code dual execution model
- Handoff JSON files in `ai-agents/shared/handoffs/`
- Multi-platform (Mac + Windows) with Dropbox coordination
- AI context bootstrap from Dropbox

**NEW workflow:**
- Features tracked as GitHub Issues using templates in `.github/ISSUE_TEMPLATE/`
- Claude Code is the sole execution agent (no GH Actions runner for feature work)
- No handoff JSON files
- Mac-only platform (office2 for server work)
- No Dropbox dependency
- Issue body is the spec; Claude Code queries `gh issue list` to find next work

---

## Section 1: Files to Archive (Mark as Superseded)

These files describe workflows that no longer exist. Do NOT delete them —
they are historical record. Add a superseded notice to the top of each.

### 1a. `docs/runbooks/agent-handbook.md`

This file references: old tooling scripts (`validate_docs.py`,
`build_registries.py`, `render_docgraph.py`), Dropbox paths, ECI path
resolution, Windows platform, `ai-agents/shared/handoffs/`,
`ai-agents/ai-context-bootstrap.md`. All of these are from the old
multi-platform era and no longer apply.

Add this block immediately after the YAML frontmatter (after the `---`):

```
> **SUPERSEDED**: This handbook describes the multi-platform workflow
> (Mac + Windows + GitHub Actions runner + handoff JSON files) which
> was retired in April 2026. The content is retained as historical
> record only. For current workflow, see `docs/runbooks/repo-governance.md`.
```

Also update the frontmatter: change `status: approved` to `status: superseded`.

### 1b. `docs/runbooks/agent-execution-roles.md`

This file describes the "Handoff Runner (GH Actions)" vs "Claude Code"
execution model. The GH Actions runner role no longer exists — Claude Code
is the sole execution agent.

Add this block immediately after the YAML frontmatter:

```
> **SUPERSEDED**: The GitHub Actions handoff runner execution model was
> retired in April 2026. Claude Code is now the sole execution agent.
> This file is retained as historical record only.
```

Update frontmatter: `status: superseded`.

### 1c. `docs/runbooks/ci-handbook.md`

This file describes AI handoff JSON validation, handoff filename
conventions, and the old registry/docgraph generation scripts. These
workflows no longer exist.

Add this block immediately after the YAML frontmatter:

```
> **SUPERSEDED**: The AI handoff JSON workflow and the registry/docgraph
> generation tooling were retired in April 2026. This file is retained
> as historical record only. For current CI behavior, see the Docs CI
> workflow in `.github/workflows/`.
```

Update frontmatter: `status: superseded`.

### 1d. `docs/runbooks/maintenance.md`

This file describes branch rulesets (`dev-human`, `dev-agent`) and the
`auto/*`/`bot/*` naming convention for GH Actions runner branches, which
no longer apply.

Add this block immediately after the YAML frontmatter:

```
> **SUPERSEDED**: The dual branch ruleset model (dev-human / dev-agent)
> and GH Actions runner branch naming conventions were retired in April
> 2026. This file is retained as historical record. For current branch
> conventions, see `docs/runbooks/repo-governance.md`.
```

Update frontmatter: `status: superseded`.

### 1e. `docs/runbooks/claude-code.md`

This file describes old slash commands (`/process-handoff`,
`/docs-self-heal`) and `.claude/config.json` permissions that no longer
apply.

Add this block immediately after the YAML frontmatter:

```
> **SUPERSEDED**: The handoff processing and docs self-heal slash commands
> described here were part of the old GitHub Actions runner workflow,
> retired in April 2026. Claude Code is still the primary execution agent
> but operates under the workflow described in CLAUDE.md and
> `docs/runbooks/repo-governance.md`.
```

Update frontmatter: `status: superseded`.

---

## Section 2: Files to Update

These files are current but contain specific stale references that need
fixing.

### 2a. `docs/runbooks/repo-governance.md`

**Change 1**: Find the Feature development section:

```
See `docs/func-spec/claude-pre-implementation-prompt.md` for the
standing orchestration directive.
```

Replace with:

```
See `CLAUDE.md` for the session initialization and issue queue query
pattern. Feature specs live in the GitHub issue queue — use
`gh issue list` to find the next work item.
```

**Change 2**: Find the Issue management → Creating issues section. After
the existing `gh issue create` command block, add:

```
### Using issue templates

GitHub issue templates are available at `.github/ISSUE_TEMPLATE/`:
- `feature.md` — new capabilities (use for all new Felix features)
- `bug.md` — defects and incorrect behavior
- `rfc.md` — design proposals and decisions
- `infra.md` — infrastructure changes with risk tier classification

Templates are applied automatically when creating issues via the
GitHub UI at: https://github.com/kentonium3/kg-automation/issues/new/choose

When creating issues via `gh` CLI, the template body must be provided
manually using `--body-file` or `--body`.
```

**Change 3**: Update `last_updated` frontmatter to today's date (2026-04-08)
and `revision` to v2.1.

### 2b. `docs/runbooks/deployment.md`

**Change 1**: Find the section referencing the feature orchestration directive:

```
See `docs/func-spec/claude-pre-implementation-prompt.md` for the
standing orchestration directive.
```

If present, replace with:

```
See `CLAUDE.md` for the current session initialization pattern.
```

**Change 2**: Find this text in the Deploy script pattern section:

```
scripts/deploy/deploy-f{NNN}.sh
```

Add a note after this line:

```
Note: Legacy deploy scripts use F-number naming (e.g., deploy-f013.sh).
New features use GitHub issue numbers. New deploy scripts should follow
the pattern: `scripts/deploy/deploy-<issue-number>.sh` or a descriptive
slug (e.g., `deploy-sysops-agent.sh`).
```

**Change 3**: Update `last_updated` to 2026-04-08.

### 2c. `docs/runbooks/felix-governance.md`

**Change 1**: Find Section 4 "New Agent Registration Procedure", Step 1:

```
3. **Add an entry to `agent-registry.json`** with:
   ...
   - `registered_by`: the feature ID
```

Change `the feature ID` to `the GitHub issue number (e.g., "#42")`.

**Change 2**: Find the commit message format in Section 4, Step 9:

```
`chore: promote <agent-name> to <level> (F###)`
```

Change to:

```
`chore: register <agent-name> at Assisted (Level 1) (#NNN)`
```

Where `#NNN` is the GitHub issue number for the feature that created
the agent.

**Change 3**: Also update Section 2 Step 9 promotion commit format:

```
`chore: promote <agent-name> to <level> (F###)`
```

Change to:

```
`chore: promote <agent-name> to <level>`
```

(No F-number reference — promotions are not tied to feature issues.)

**Change 4**: Update `last_updated` to 2026-04-08.

### 2d. `docs/runbooks/spec-kitty-init-in-existing-repo.md`

This is a one-time setup guide that was used during initial spec-kitty
installation. The project already has spec-kitty installed. Add a notice
at the top (after frontmatter) clarifying its status:

```
> **HISTORICAL**: spec-kitty is already installed and configured in this
> repository. This guide documents the steps that were followed during
> initial setup. It is retained for reference in case of reinstallation
> or migration. The current spec-kitty workflow is documented in CLAUDE.md.
>
> Note: Step 5 "Create Project Constitution" uses the old spec-kitty 1.x
> terminology. In spec-kitty 3.x, this is now called a "charter" and is
> managed via `spec-kitty charter interview`. The Felix Constitution at
> `docs/constitution/FELIX-CONSTITUTION.md` is a separate document from
> the spec-kitty charter at `.kittify/charter/charter.md`.
```

Update frontmatter: change `status: draft` to `status: historical`.

---

## Section 3: New Runbook to Create

### 3a. Create `docs/runbooks/github-issues-workflow.md`

Write the following file to
`/Users/kentgale/repos/kg-automation/docs/runbooks/github-issues-workflow.md`:

---
title: GitHub Issues Workflow
doc_type: runbook
audience: agents_and_humans
status: approved
last_updated: '2026-04-08'
revision: v1.0
---

# GitHub Issues Workflow

GitHub Issues is the planning record for all Felix features, bugs, and
infrastructure changes. This runbook covers the full issue lifecycle from
creation to closure.

## Issue anatomy

Every issue has:
- **Title**: `<Type>: <Short description>` (e.g., `Feature: Remote diagnostics via WhatsApp`)
- **Type**: GitHub native type — Bug, Feature, RFC, or Infra
- **P-label**: One triage label encoding priority and type (e.g., `P1-feature`, `P1-bug`)
- **Area label**: One or more domain labels (e.g., `area/ea`, `area/infrastructure`)
- **Milestone**: The capability cluster this issue belongs to
- **Body**: The spec — written using the appropriate issue template

Issues without a P-label are untriaged. Gaining a P-label is the triage decision.

## Creating an issue

### Via GitHub UI (preferred for feature/RFC creation)

Go to https://github.com/kentonium3/kg-automation/issues/new/choose
and select the appropriate template. Templates are at `.github/ISSUE_TEMPLATE/`.

### Via gh CLI

```bash
# Create with labels and milestone
gh issue create \
  --repo kentonium3/kg-automation \
  --title "Feature: <description>" \
  --label "P3-candidate,area/ea" \
  --milestone "EA-Calendaring" \
  --body-file /path/to/body.md

# Create inline
gh issue create \
  --repo kentonium3/kg-automation \
  --title "Bug: <description>" \
  --label "P1-bug,area/task-intel" \
  --body "## Summary\n..."
```

### Via WhatsApp (once F022 is live)

Dictate the issue description to Felix. Felix will propose labels,
milestone, and issue type, then create the issue on confirmation.

## Triage

New issues arrive with `P3-candidate` from the template default. Triage
assigns the final P-label:

1. Read the issue body
2. Confirm or assign area/ label(s)
3. Assign to the appropriate milestone
4. Replace `P3-candidate` with the correct P-label
5. Add to the Felix Roadmap project board

```bash
# Relabel
gh issue edit <number> \
  --repo kentonium3/kg-automation \
  --add-label "P1-feature" \
  --remove-label "P3-candidate"

# Assign milestone
gh issue edit <number> \
  --repo kentonium3/kg-automation \
  --milestone "EA-Calendaring"
```

## Finding the next work item (Claude Code)

```bash
# Find highest priority open features in active milestone
gh issue list \
  --repo kentonium3/kg-automation \
  --label P1-feature \
  --state open \
  --limit 5 \
  --json number,title,body,labels,milestone

# Find all P1 items across types
gh issue list \
  --repo kentonium3/kg-automation \
  --search "label:P1-feature OR label:P1-bug OR label:P1-infra" \
  --state open \
  --json number,title,labels,milestone
```

Read the full issue body before starting — it is the spec.

## Issue body as spec

The issue body replaces the old `docs/func-spec/F0NN_*.md` files.
The body follows the template structure:

- **Feature issues**: Executive summary, problem statement, study these
  files first, functional requirements with acceptance criteria
  checkboxes, out of scope, architecture impact, constitutional compliance
- **Bug issues**: Summary, reproduction, expected vs actual, root cause,
  suggested fix, success criteria
- **RFC issues**: Question, options, recommendation, decision record
- **Infra issues**: Summary, risk tier, services affected, pre-flight,
  rollback, verification

GitHub tracks checkbox completion percentage automatically — this is the
progress indicator replacing success criteria checklists in old func-specs.

## Closing an issue

Close when the implementing PR is merged:

```bash
gh issue close <number> \
  --repo kentonium3/kg-automation \
  --comment "Resolved in <commit-hash>. <Brief note on what was done.>"
```

For RFC issues, record the decision in the Decision record section before
closing:

```bash
gh issue edit <number> \
  --repo kentonium3/kg-automation \
  --body "<updated body with decision record filled in>"
gh issue close <number> --repo kentonium3/kg-automation
```

## Project board

The Felix Roadmap project at https://github.com/users/kentonium3/projects/1
provides three views: Board (by milestone), Table (by priority), Roadmap.

Add an issue to the project after creation:

```bash
# Get project number
gh project list --owner kentonium3

# Add issue (unset GITHUB_TOKEN first if set — project scope uses CLI auth)
unset GITHUB_TOKEN
gh project item-add <project-num> \
  --owner kentonium3 \
  --url https://github.com/kentonium3/kg-automation/issues/<number>
```

## Issue templates reference

| Template | Use for | Default label |
|----------|---------|---------------|
| `feature.md` | New capabilities | P3-candidate |
| `bug.md` | Defects | P3-candidate |
| `rfc.md` | Design decisions | P1-rfc |
| `infra.md` | Infrastructure changes | P3-candidate |

Templates enforce consistent structure. The `config.yml` disables blank
issues — all issues must use a template.

## Label reference

See `docs/runbooks/repo-governance.md` for the full label taxonomy.

---

## Section 4: Verify and Commit

After making all changes in Sections 1–3:

```bash
cd /Users/kentgale/repos/kg-automation

# Verify all modified files
git diff --name-only

# Confirm new file created
ls docs/runbooks/github-issues-workflow.md

# Stage and commit
git add docs/runbooks/
git commit -m "docs: audit and update runbooks for issue-queue workflow

- Archive 5 runbooks from retired multi-platform / runner workflow
- Update repo-governance, deployment, felix-governance with new refs
- Add historical notice to spec-kitty-init guide
- Create github-issues-workflow.md as new canonical reference"
```

---

## Section 5: Checklist

- [ ] `agent-handbook.md` — superseded notice added, status updated
- [ ] `agent-execution-roles.md` — superseded notice added, status updated
- [ ] `ci-handbook.md` — superseded notice added, status updated
- [ ] `maintenance.md` — superseded notice added, status updated
- [ ] `claude-code.md` — superseded notice added, status updated
- [ ] `repo-governance.md` — func-spec reference removed, template section added
- [ ] `deployment.md` — orchestration directive reference updated, deploy script note added
- [ ] `felix-governance.md` — F-number refs replaced with issue numbers
- [ ] `spec-kitty-init-in-existing-repo.md` — historical notice added
- [ ] `docs/runbooks/github-issues-workflow.md` — new file created
- [ ] Committed to main

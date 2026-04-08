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
  files first, assumptions, functional requirements with acceptance
  criteria checkboxes, out of scope, architecture impact, constitutional
  compliance
- **Research issues**: Research purpose, research questions (RQ-X) with
  acceptable answer forms, known sources, evaluation criteria (if
  comparative), expected outputs, success criteria including downstream
  readiness
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
| feature.md | New capabilities (software-dev missions) | P3-candidate |
| research.md | Investigations that must complete before a feature can be specced | P3-candidate |
| bug.md | Defects | P3-candidate |
| rfc.md | Design decisions | P1-rfc |
| infra.md | Infrastructure changes | P3-candidate |
| docs-debt.md | Documentation gaps or outdated content | P2-debt |

Templates enforce consistent structure. The `config.yml` disables blank
issues — all issues must use a template.

### Choosing between feature and research templates

Use **feature** when the work produces code, config, or infrastructure
changes — the body becomes the input to `/spec-kitty.specify` for a
`software-dev` mission.

Use **research** when the work produces findings and a recommendation
that unblock a subsequent feature — the body becomes the input to
`/spec-kitty.specify --mission research`. Research issues define
research questions (RQ-X) with acceptable answer forms, not functional
requirements (FR-X).

Use **docs-debt** when an audit or review identifies a documentation
gap — these are typically created automatically by the doc-audit
workflows or manually during review.

## Label reference

See `docs/runbooks/repo-governance.md` for the full label taxonomy.

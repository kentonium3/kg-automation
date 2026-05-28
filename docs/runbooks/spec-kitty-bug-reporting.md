---
title: Spec-Kitty Bug Reporting
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-28
last_validated: 2026-05-28
last_updated: '2026-05-28'
version: v1.0
owners: [kgale]
---

# Spec-Kitty Bug Reporting

How we track and report suspected bugs in `spec-kitty` (and sibling tooling
like codex, antigravity, openclaw). The workflow is a **dual-track model**:
internal status tracking lives as a GitHub issue in `kentonium3/kg-automation`;
when ready to file upstream, a slim external paste-buffer doc is generated
from the issue body. The two surfaces have different audiences and different
content shapes.

## Why dual-track

Past practice put both internal status and external bug reports in
`docs/diagnostics/*.md`, with a filename-prefix lifecycle (`xx_` → `NNNN_`
→ `fixed_NNNN_` → archive). That conflated two distinct concerns:

- **Internal**: priority, status, suggested fix, open questions, next steps,
  cross-references to our project's issues and missions, environment context
- **External**: the minimum the maintainer needs to reproduce and fix the bug
  — summary, reproduction, environment

The new model separates these. Internal lives where status tracking is
ergonomic (GitHub issues — labels, comments, cross-links, query filters,
close/reopen state). External is a one-shot paste buffer with only the
fields the maintainer benefits from.

## Surfaces

| Artifact | Path | Audience |
|---|---|---|
| **Internal issue template** | `.github/ISSUE_TEMPLATE/spec-kitty-bug.md` | Used as the body of new kg-automation issues |
| **External paste template** | `docs/diagnostics/spec-kitty-bug-report-external-template.md` | Source for upstream submission |
| **Per-report paste buffer** | `docs/diagnostics/{issue#-or-slug}-external.md` | Generated when filing upstream; transient |
| **Historical archive** | `docs/archive/spec-kitty-feedback/` | Reports for fixed/closed upstream issues |

## Lifecycle

```text
1. OBSERVE          Suspected spec-kitty bug surfaces during work.
2. FILE INTERNAL    gh issue create in kentonium3/kg-automation with the
                    internal template; label area/tooling; spec: brief.
3. INVESTIGATE      Edit the issue body / add comments as evidence and
                    root-cause analysis accumulate. Internal status tracked
                    via labels (P1-bug, P2-bug, etc.) and issue state.
4. GENERATE EXTERNAL  Populate the slim template into a paste doc at
                    docs/diagnostics/{slug}-external.md. Strip all the
                    internal-only fields (priority/status/suggested fix/
                    open questions/next steps/internal refs).
5. FILE UPSTREAM    Paste the external doc into Priivacy-ai/spec-kitty's
                    issue UI (or, once trusted, gh issue create --repo
                    Priivacy-ai/spec-kitty --body-file <path>).
6. CROSS-LINK       Edit the kg-automation issue body to add
                    "Upstream: Priivacy-ai/spec-kitty#NNNN" and apply
                    the upstream-filed label.
7. CLOSE            When upstream ships the fix AND we've verified it
                    locally, close the kg-automation issue. Move the paste
                    doc to docs/archive/spec-kitty-feedback/{NNNN}-external.md
                    or delete it (paste docs are transient by design).
```

## When to file (and not file)

**File a bug report when**:

- Behavior contradicts documentation, command help text, or a flag's name
- A spec-kitty command silently corrupts or destroys user-authored data
- Workflow produces inconsistent state that requires manual recovery
- Recurring behavior that required manual compensation across multiple sessions

**Don't file when**:

- One-off errors that didn't reproduce after investigation
- User error (misused flag, wrong working directory)
- Feature requests or enhancements — file those as proposals on Priivacy-ai/spec-kitty directly

## Required evidence

Before promoting an internal issue to upstream-ready:

- At least one reproducible path (even if not minimal)
- Command output showing the unexpected behavior
- Git diff or state snapshot showing data loss/mutation if applicable
- Environment: OS, Python version, `spec-kitty --version`, `codex --version` or other relevant tool versions

## Labels

- `area/tooling` — canonical area label for spec-kitty bugs (and sibling tooling: codex, antigravity, openclaw)
- `spec: brief` — default state when filed; not yet structured for the spec-kitty mission workflow (these issues usually stay `spec: brief` forever since fixes land upstream, not in our repo)
- `upstream-filed` — applied at lifecycle step 6 (FILE UPSTREAM → CROSS-LINK) once we have an upstream issue number. The issue body should also carry an `Upstream: <repo>#<n>` line. The label is the at-a-glance signal in queue views; the body link is the navigable cross-reference.
- Priority labels (`P1-bug`, `P2-bug`, etc.) — applied based on operational impact

## The two templates

### Internal template (`.github/ISSUE_TEMPLATE/spec-kitty-bug.md`)

Rich format used as the body of new kg-automation issues. Includes:

- Summary
- Spec-Kitty version + relevant agent versions (codex, antigravity, etc.)
- Reproduction (Prereqs / Steps / Expected / Actual)
- Root Cause (if known)
- Workaround Applied (with cross-refs to our internal issues if relevant)
- Suggested Fix (Options A/B/C if applicable)
- Impact
- Environment
- Open Questions
- Next Steps
- Discovered (when, by whom, during what mission)
- Upstream link (populated once filed)

### External template (`docs/diagnostics/spec-kitty-bug-report-external-template.md`)

Slim format used as the source for upstream paste docs. Drops:

- No frontmatter
- No date (the upstream issue tracks creation date)
- No priority (not for us to set)
- No status (their labels)
- No Suggested Fix (maintainer knows how to fix)
- No Open Questions or Next Steps (internal)
- No internal issue/mission/WP references

Keeps: Summary, Reproduction, Root Cause (only if known), Workaround Applied (trimmed of internal refs), Environment.

## Cross-references

- [`docs/diagnostics/spec-kitty-workflow-journal.md`](<../diagnostics/spec-kitty-workflow-journal.md>) — running observations log; not a bug-tracker. Promote a journal entry to an internal issue when it stabilizes into a reproducible bug.
- [`docs/archive/spec-kitty-feedback/`](<../archive/spec-kitty-feedback/>) — historical record of resolved upstream issues, preserved for context.

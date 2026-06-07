---
title: Spec-Kitty Bug Reporting
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-28
last_validated: 2026-06-07
last_updated: '2026-06-07'
version: v1.2
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
1. OBSERVE              Suspected spec-kitty bug surfaces during work.
2. FILE INTERNAL        gh issue create in kentonium3/kg-automation with
                        the internal template; label area/tooling; spec: brief.
3. INVESTIGATE          Edit the issue body / add comments as evidence and
                        root-cause analysis accumulate. Internal status tracked
                        via labels (P1-bug, P2-bug, etc.) and issue state.
4. GENERATE EXTERNAL    Populate the slim template into a paste doc at
                        docs/diagnostics/{slug}-external.md. Strip all the
                        internal-only fields (priority/status/suggested fix/
                        open questions/next steps/internal refs). Add the
                        attribution + reviewer-approval footer (see template).
5. PRE-FILING APPROVAL  Surface the proposed upstream title in the internal
                        tracking issue body (above the embedded draft section).
                        Operator reviews and approves the title AND the body
                        BEFORE the upstream filing step. Never file upstream
                        on the agent's own initiative.
6. FILE UPSTREAM        Paste the external doc into Priivacy-ai/spec-kitty's
                        issue UI (or, once trusted, gh issue create --repo
                        Priivacy-ai/spec-kitty --title "<approved title>"
                        --body-file <path>).
7. CROSS-LINK           Edit the kg-automation issue body to add the
                        "Filed upstream: Priivacy-ai/spec-kitty#NNNN" header
                        with the approved title, apply the upstream-filed
                        label, and create the diagnostic snapshot at
                        docs/diagnostics/{NNNN}_{short-slug}.md.
8. CLOSE                When upstream ships the fix AND we've verified it
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

**Attribution + reviewer-approval footer (mandatory, added 2026-06-04 / v1.1; structured form added 2026-06-07 / v1.2):**

Every external paste MUST end with a footer block of the form:

```markdown
---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 4.7), YYYY-MM-DD.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), YYYY-MM-DD.
**Local tracking**: kentonium3/kg-automation#NNN.
```

Field rules:
- **Authored by** — Kent's real name + GH org/repo identifier `(kentonium3/kg-automation)` so upstream maintainers can resolve the operator without guesswork, joined with `&` to the drafting agent's identity. Agent identity should include the specific model (e.g. `Claude Code (Claude Opus 4.7)`, `Codex (gpt-5.5)`, `Antigravity (gemini-2.5-pro)`). Date is the day the draft was authored.
- **Submission approved by** — Kent's real name + GH org/repo identifier, repeated. This line is the operator-in-the-loop approval declaration. Date is the day of upstream filing (typically same day or one day after authoring).
- **Local tracking** — direct link back to the kentonium3/kg-automation tracking issue, so upstream maintainers can navigate to our internal context if useful.

Rationale: bug reports filed in upstream trackers carry an implicit author voice. The structured 3-line form (v1.2, 2026-06-07) replaces the prior single-line attribution because Kent wanted the human-in-the-loop approval declaration to be unmistakably explicit — separating authoring (collaborative) from submission approval (Kent-only) makes accountability clear and prevents any reading of the report as unattended-agent output. The local-tracking link gives maintainers a one-click path back to our internal queue without requiring a separate "ours: #NNN" cross-reference in the body proper.

## Pre-filing approval checklist (operator-facing)

Before the agent files upstream, the operator must see and approve, in the internal tracking issue body:

1. **The proposed upstream title** — exact text, in a clearly-labelled "Proposed upstream title" section above the embedded draft body.
2. **The embedded draft body** — in a code block, ready-to-paste, including the attribution + reviewer-approval footer.

The agent's filing-step prompt to the operator should be of the form: *"Approve title `<title>` and body for upstream filing?"* — explicitly state the title, do not assume the operator will infer it from the embedded body.

## Cross-references

- [`docs/diagnostics/spec-kitty-workflow-journal.md`](<../diagnostics/spec-kitty-workflow-journal.md>) — running observations log; not a bug-tracker. Promote a journal entry to an internal issue when it stabilizes into a reproducible bug.
- [`docs/archive/spec-kitty-feedback/`](<../archive/spec-kitty-feedback/>) — historical record of resolved upstream issues, preserved for context.

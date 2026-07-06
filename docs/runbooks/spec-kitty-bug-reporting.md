---
title: Spec-Kitty Bug Reporting
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-28
last_validated: 2026-07-05
last_updated: '2026-07-05'
version: v1.4
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
| **External paste template** | `docs/diagnostics/spec-kitty-bug-report-external-template.md` | Reference for the slim upstream-body shape — embed it directly in the internal issue, no separate paste file |
| ~~Per-report paste buffer~~ | ~~`docs/diagnostics/{issue#-or-slug}-external.md`~~ | **DEPRECATED 2026-06-08 (v1.3)** — embed the upstream draft directly in the internal issue body instead. See v1.3 change note below. |
| **Historical archive** | `docs/archive/spec-kitty-feedback/` | Reports for fixed/closed upstream issues |

## Lifecycle (v1.3, 2026-06-08)

```text
1. OBSERVE              Suspected spec-kitty bug surfaces during work.
2. FILE INTERNAL        gh issue create in kentonium3/kg-automation with
                        the internal template; label area/tooling; spec: brief.
                        **When the bug is already understood well enough to draft
                        the upstream report (the common case), embed the upstream
                        draft in this SAME issue body in one shot** (step 4 shape),
                        so Kent reviews the internal tracker AND the upstream copy
                        together in a single pass. Filing internal in
                        kg-automation needs no pre-review (repo-scoped exception in
                        the cross-repo standing rules); only the upstream filing
                        (step 5/6) is gated.
3. INVESTIGATE          Edit the issue body / add comments as evidence and
                        root-cause analysis accumulate. Internal status tracked
                        via labels (P1-bug, P2-bug, etc.) and issue state.
4. EMBED UPSTREAM DRAFT If not already embedded at creation (step 2 — preferred),
                        add a "Proposed upstream title" section and an
                        "Embedded upstream draft (paste-ready)" code block
                        directly inside the internal issue body. The embedded
                        draft uses the slim shape from the external template
                        (Summary / Reproduction / Root Cause if known /
                        Workaround Applied / Environment / attribution+approval
                        footer) — Suggested Fix, Open Questions, Next Steps,
                        internal refs, frontmatter, and dates are all dropped.
                        Use a 4-backtick outer fence so the draft's inner
                        ```bash/```text fences stay verbatim and paste-ready.
                        No separate paste file.
5. PRE-FILING APPROVAL  Operator reviews and approves BOTH the proposed
                        title AND the embedded draft body in the internal
                        issue, BEFORE the upstream filing step. Never file
                        upstream on the agent's own initiative.
6. FILE UPSTREAM        gh issue create --repo Priivacy-ai/spec-kitty
                        --title "<approved title>" --body-file <(extract the
                        embedded draft from the internal issue + fill the
                        Submission approved date with today).
7. CROSS-LINK           Comment on the kg-automation issue with the
                        "Filed upstream: Priivacy-ai/spec-kitty#NNNN" line +
                        filing-date + label transitions. Apply the
                        upstream-filed label. No separate diagnostic snapshot
                        file needed (the internal issue is the snapshot).
8. CLOSE                When upstream ships the fix AND we've upgraded
                        locally to a release that consumes it, transition
                        labels upstream-filed → upstream-pending-release →
                        upstream-released and close the kg-automation issue.
```

### v1.4 change note (2026-07-05)

Two changes: (1) **Embed the upstream draft at issue creation** (step 2), not as a
separate later step — when the bug is understood well enough to draft the upstream
report, create the internal issue with the embedded draft already in the body so Kent
reviews both surfaces in one pass. Step 4 remains as the fallback for drafts added
during investigation. (2) Recorded the **repo-scoped copy-approval exception**: internal
`kentonium3/kg-automation` posts need no pre-review (Kent's own tracking repo); only
copy leaving the repo — the upstream filing — stays gated. Both driven by operator
preference given 2026-07-05.

### v1.3 change note (2026-06-08)

v1.2 (and prior) required generating a transient paste file at
`docs/diagnostics/{slug}-external.md` as an intermediate artifact. v1.3
removes that step: the upstream-bound draft is embedded directly in the
internal kg-automation issue body, in a code block, ready to copy into
`gh issue create --body-file`. The shape of the embedded draft still
follows the slim external template — only the file artifact is removed.

Why: the paste file added a maintenance surface (frontmatter staleness,
status drift, the question of whether to archive vs delete on close) for
zero net value over a code block inside the GitHub issue. Existing paste
docs under `docs/diagnostics/*-external.md` may stay as-is for already-filed
issues; new bug filings should NOT generate one.

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

Slim format that defines the shape of the upstream-bound draft. As of v1.3 (2026-06-08), this template is consulted as a **shape reference** — embed the draft directly into the internal issue body (lifecycle step 4) rather than generating a separate paste file. Drops:

- No frontmatter
- No date (the upstream issue tracks creation date)
- No priority (not for us to set)
- No status (their labels)
- No Suggested Fix (maintainer knows how to fix)
- No Open Questions or Next Steps (internal)
- No internal issue/mission/WP references

Keeps: Summary, Reproduction, Root Cause (only if known), Workaround Applied (trimmed of internal refs), Environment.

**Attribution + reviewer-approval footer (mandatory, added 2026-06-04 / v1.1; structured form added 2026-06-07 / v1.2):**

Every embedded upstream draft MUST end with a footer block of the form:

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

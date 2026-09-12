---
title: Spec-Kitty External Bug Report Template
doc_type: reference
status: approved
audience: humans
last_updated: '2026-09-11'
version: v1.3
---

# Spec-Kitty External Bug Report Template

Slim template for submitting bug reports to upstream tool projects
(`spec-kitty/spec-kitty`, openai/codex, etc.). Internal status tracking
happens in a kg-automation GitHub issue (see
[`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>));
this template defines the **shape** of the upstream-bound draft.

**Do not generate a separate paste file.** Since runbook v1.3 (2026-06-08)
the draft is embedded directly in the internal kg-automation issue body,
inside a 4-backtick fenced block, ready to copy into
`gh issue create --body-file`. The former per-report paste docs at
`docs/diagnostics/{slug}-external.md` are deprecated; existing ones may
stay for already-filed issues, but new filings must not create them.

**What this template excludes vs. the internal issue body** (intentional):

- No frontmatter (the upstream issue tracker has its own metadata)
- No date (the issue tracks creation)
- No priority (the maintainer triages)
- No status (their labels)
- No suggested fix (maintainer knows their codebase)
- No open questions (internal)
- No next steps (internal)
- No references to our project's issues, missions, or work-package numbers

**What this template keeps**:

- Summary — one paragraph
- Reproduction — Prerequisites / Steps / Expected / Actual
- Root Cause — only if known; helps maintainer triage
- Workaround Applied — trimmed of internal refs; signals impact severity
- Environment — required for reproduction
- **Attribution + reviewer-approval footer** (added 2026-06-04 / v1.1) — declares the human-in-the-loop production path so maintainers know the report was reviewed before submission

---

## Template body (copy below this line into the upstream issue)

# Bug: {short title}

## Summary

{One paragraph. What goes wrong and why it matters. 4-5 sentences max.}

## Reproduction

### Prerequisites

- {Preconditions: tool versions, project state, OS}
- {Workflow position required to hit the bug}

### Steps

```bash
{exact commands to reproduce}
```

### Expected Behavior

{What should happen per documentation, command name, or reasonable expectations.}

### Actual Behavior

{What actually happens. Include command output verbatim.}

```text
{command output / error message}
```

## Root Cause

<!--
Optional. Include only if known or strongly suspected. Reference source
files in the upstream package if you've traced it. Skip entirely if
unknown — let maintainers form their own theory.
-->

## Workaround Applied

<!--
Optional. What users have done to keep working. Strip internal cross-refs
(issue numbers, mission slugs, internal helper script names). The signal
to maintainers: this bug is impactful enough that workarounds are needed
in the field.

Example (good): "Patched the affected file to drop the deprecated flag.
Re-applied via a small script after each tool refresh."

Example (bad — keeps internal refs): "Filed our issue #330; patched per
the diagnostic at docs/diagnostics/xxx; tracked in feedback memory entry."
-->

## Environment

- OS: {e.g., macOS Darwin 25.5.0 / Windows 11 26200}
- Python: {e.g., 3.13.7}
- spec-kitty-cli: {X.Y.Z (pinned tag SHA <9char>) or X.Y.Z (main build, SHA <9char>)}
- Install method: {e.g., uv tool install from PyPI / pipx from git main}
- {Other relevant tool versions: codex, antigravity, gog, etc.}

<!--
The 9-char build SHA is MANDATORY - a bare version string does not identify
a build. Resolve it per the Build-ID convention in
runbooks/spec-kitty-bug-reporting.md, and name the repository line alongside it.
-->

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & {agent name — Claude Code (Claude Opus 5), Codex (gpt-5.5), Antigravity (gemini-…), etc.}, {YYYY-MM-DD}.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), {YYYY-MM-DD}.
**Local tracking**: kentonium3/kg-automation#{NNN}.

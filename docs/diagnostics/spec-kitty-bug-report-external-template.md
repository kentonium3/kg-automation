---
title: Spec-Kitty External Bug Report Template
doc_type: reference
status: approved
audience: humans
last_updated: '2026-06-04'
version: v1.1
---

# Spec-Kitty External Bug Report Template

Slim template for submitting bug reports to upstream tool projects
(`Priivacy-ai/spec-kitty`, openai/codex, etc.). Internal status tracking
happens in a kg-automation GitHub issue (see
[`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>));
this template is the source for the paste buffer that goes into the
upstream issue tracker.

**Generated paste docs live at**: `docs/diagnostics/{slug}-external.md`
(transient; archived or deleted once the upstream issue is filed and
closed).

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

- OS: {e.g., macOS Darwin 25.5.0}
- Python: {e.g., 3.13.x}
- {tool}-cli: {version}
- {Other relevant tool versions: codex, antigravity, gog, etc.}

---

*Authored by Kentonium3 and {agent name — Claude, Codex, Antigravity, etc.}. Reviewed and approved by Kentonium3 for submission.*

---
title: "Bug Report: {short title}"
doc_type: diagnostic
status: active
---
# Bug Report: {short title}

**Date**: YYYY-MM-DD
**Spec-Kitty Version**: {x.y.z}
**Reporter**: {name} (via {agent or tool})
**Priority**: {Critical | High | Medium | Low} — {one-line impact}
**Status**: <PENDING INVESTIGATION | READY TO FILE | FILED <#issue> | FIXED in {version}>

## Summary

{One-paragraph problem statement. What went wrong and why it matters. No more than 4-5 sentences.}

## Reproduction

### Prerequisites

- {Preconditions required to hit the bug}
- {State the repo/feature/workflow must be in}

### Steps

```bash
{exact commands to reproduce}
```

### Expected Behavior

{What should happen according to documentation, command name, or reasonable expectations.}

### Actual Behavior

{What actually happens. Include command output verbatim when available.}

```text
{command output / error message / diff showing the unexpected mutation}
```

### Root Cause

{If known or strongly suspected, describe the mechanism. Link to source files in the spec-kitty-cli package if reproducible.}

## Workaround Applied ({Feature ID})

{Describe what the user/agent did to work around the bug. Include exact commands if they were run, and call out any manual steps that violated normal workflow.}

```bash
{workaround commands}
```

## Suggested Fix

Option A: {primary recommendation}

Option B: {alternative approach}

Option C: {fallback / defensive option}

## Impact

- {Who hits this and how often}
- {What work is lost or corrupted if not worked around}
- {Downstream consequences in the spec-kitty workflow}

## Environment

- OS: {e.g., macOS Darwin 25.3.0}
- Python: {e.g., 3.13.12}
- spec-kitty-cli: {version}
- Feature: {feature-slug where bug observed}

## Open Questions

1. **{Question about root cause, scope, or behavior under different conditions}?**
   {Context + what's unknown.}

2. **{Question about fix design or compatibility}?**
   {Context.}

## Next Steps

- {Action needed to validate, reproduce more cleanly, or file upstream}
- {Data to gather before filing}

## Discovered

YYYY-MM-DD by {name/agent} during {feature or workflow context}

---

## Template Usage Notes

**When to create a new bug report**:

- Behavior contradicts documentation, command help text, or a flag's name
- Workflow produces corrupted/inconsistent state
- A spec-kitty command silently destroys user-authored data
- Recurring behavior that required manual compensation

**When NOT to create a bug report**:

- One-off errors that didn't reproduce after investigation
- User error (misused flag, wrong working directory)
- Feature requests or enhancements (file as proposal instead)

**Required evidence for filing**:

- At least one reproducible path (even if not minimal)
- Command output showing the unexpected behavior
- Git diff or state snapshot showing data loss/mutation if applicable
- Environment details (version, OS, Python)

**Cross-reference the running journal**:

The [spec-kitty workflow journal](<../spec-kitty-workflow-journal.md>) captures
observations during feature work. Promote an entry to a standalone bug report
here when:

- The observation has stabilized into a reproducible bug
- You have enough evidence to write a minimal repro
- The issue warrants upstream attention from the spec-kitty maintainer

Link the report back to the journal entry via the `## Discovered` section.

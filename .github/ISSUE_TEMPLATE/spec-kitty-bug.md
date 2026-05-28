---
name: Spec-Kitty (or sibling tooling) bug
about: Track a suspected bug in spec-kitty, codex, antigravity, openclaw, or related tooling. Internal status tracker; the external upstream report is generated from the body when filing.
title: "Tooling: "
labels: ["area/tooling", "spec: brief"]
assignees: ''
---

<!--
Internal status-tracker for tooling bugs we may file upstream. Keep the
rich format here; generate a slim external paste doc from this body using
the template at docs/diagnostics/spec-kitty-bug-report-external-template.md
when ready to file upstream.

See docs/runbooks/spec-kitty-bug-reporting.md for the full workflow.
-->

## Summary

<!--
One-paragraph problem statement. What went wrong and why it matters. 4-5
sentences max.
-->

## Versions

- **spec-kitty-cli**:
- **codex / antigravity / other relevant agent CLI**:
- **OpenClaw** (if relevant):

## Reproduction

### Prerequisites

-

### Steps

```bash

```

### Expected Behavior



### Actual Behavior

```text

```

## Root Cause

<!--
If known or strongly suspected. Link to source files in the upstream
package if reproducible. Skip if you don't know yet.
-->

## Workaround Applied

<!--
What we did to keep working while the bug is unfixed. Cross-reference our
internal issues, helper scripts, or local patches if relevant. This section
will be TRIMMED of internal refs when generating the external paste doc.
-->

## Suggested Fix

<!--
Optional. Options A/B/C if applicable. EXCLUDED from the external paste
doc — maintainers know how to fix.
-->

## Impact

- **Who hits this**:
- **Frequency**:
- **What breaks**:
- **Severity** (data loss / workflow friction / cosmetic):

## Environment

- OS:
- Python:
- Anything else relevant (codex CLI version, gog version, etc.):

## Open Questions

<!--
Things we're unsure about — root cause variants, scope, behavior under
different conditions. Internal-only; EXCLUDED from the external paste doc.
-->

## Next Steps

<!--
What needs to happen before filing upstream, or before this can be closed.
Internal-only; EXCLUDED from the external paste doc.
-->

## Discovered

<!--
YYYY-MM-DD by {name/agent} during {feature or workflow context}.
-->

## Upstream

<!--
Populate when filed and apply the upstream-filed label:
Upstream: Priivacy-ai/spec-kitty#NNNN (or other upstream repo)
-->
